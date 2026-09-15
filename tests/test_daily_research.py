import json

import numpy as np
import pandas as pd
import pytest

from multifactor_platform.artifacts import load_dataset, replay_run, save_dataset, save_run
from multifactor_platform.backtesting.comparison import common_evaluation_window
from multifactor_platform.backtesting.engine import run_top_n_backtest
from multifactor_platform.backtesting.ledger import simulate_daily_ledger
from multifactor_platform.research import ResearchDataError
from multifactor_platform.risk.exposures import compute_factor_exposures


def market(dates, a, b=None):
    series = {'A': a, 'SPY': [100.] * len(dates)}
    if b is not None:
        series['B'] = b
    return pd.DataFrame([{'date': pd.Timestamp(date), 'ticker': ticker, 'adj_close': float(price)}
                         for ticker, values in series.items() for date, price in zip(dates, values)])


def test_daily_cash_nav_and_trade_reconciliation():
    prices = market(['2024-02-01', '2024-02-02', '2024-02-05', '2024-02-06'],
                    [100, 110, 90, 95], [100, 90, 120, 130])
    targets = pd.DataFrame({'date': pd.to_datetime(['2024-02-01', '2024-02-05']),
                            'ticker': ['A', 'B'], 'weight': [.8, .8]})
    output = simulate_daily_ledger(prices, targets, '2024-02-01', '2024-02-06',
                                   initial_capital=1000, commission_bps=10, slippage_bps=20,
                                   annual_cash_rate=.05)
    ledger = output['daily_ledger']
    assert ledger.iloc[0].nav == pytest.approx(1000 / (1 + .003 * .8))
    assert ledger.iloc[2].cash_interest == pytest.approx(
        ledger.iloc[1].cash * (1.05 ** (3 / 365.25) - 1))
    np.testing.assert_allclose(ledger.nav, ledger.cash + ledger.positions_value)
    np.testing.assert_allclose(ledger.nav, ledger.opening_nav + ledger.market_pnl +
                               ledger.cash_interest - ledger.commission - ledger.slippage)
    assert (1 + ledger.daily_return).prod() == pytest.approx(ledger.nav.iloc[-1] / 1000)
    for date, trades in output['trades'].groupby('date'):
        np.testing.assert_allclose(trades.notional, trades.adjusted_units * trades.adjusted_price)
        assert trades.commission.sum() == pytest.approx(ledger.loc[date, 'commission'])
        assert trades.slippage.sum() == pytest.approx(ledger.loc[date, 'slippage'])
        assert (trades.notional.abs().sum() == pytest.approx(ledger.loc[date, 'traded_notional']))
    holdings = output['daily_holdings']
    np.testing.assert_allclose(holdings.market_value, holdings.adjusted_units * holdings.adjusted_price)


def test_daily_drawdown_and_terminal_mark_are_not_hidden_by_monthly_recovery():
    prices = market(['2024-01-31', '2024-02-01', '2024-02-15', '2024-02-29', '2024-03-01', '2024-03-05'],
                    [100, 100, 50, 100, 100, 120])
    rankings = pd.DataFrame({'date': pd.to_datetime(['2024-01-31', '2024-02-29']),
                             'ticker': ['A', 'A'], 'rank': [1., 1.]})
    result = run_top_n_backtest(rankings, prices, n=1, cost_bps=0)
    assert result['metrics']['max_drawdown'] == pytest.approx(-.5)
    assert result['daily_ledger'].nav.iloc[-1] == pytest.approx(1_200_000)
    assert (1 + result['returns']).prod() == pytest.approx(1.2)
    assert result['settings']['evaluation_end'] == '2024-03-05'
    assert result['rebalance_log'].next_trade_date.iloc[-1] == pd.Timestamp('2024-03-05')
    assert result['metrics']['cagr'] == pytest.approx(1.2 ** (365.25 / 33) - 1)


def test_missing_midperiod_price_is_rejected_even_when_endpoints_exist():
    prices = market(['2024-02-01', '2024-02-02', '2024-02-05'], [100, np.nan, 100])
    targets = pd.DataFrame({'date': pd.to_datetime(['2024-02-01']), 'ticker': ['A'], 'weight': [1.]})
    with pytest.raises(ResearchDataError, match='daily prices'):
        simulate_daily_ledger(prices, targets, '2024-02-01', '2024-02-05')


def test_all_cash_has_no_stock_pnl_and_receives_cash_interest():
    prices = market(['2024-02-01', '2024-02-02', '2024-02-05'], [100, 10, 200])
    targets = pd.DataFrame({'date': pd.to_datetime(['2024-02-01']), 'ticker': ['A'], 'weight': [0.]})
    output = simulate_daily_ledger(prices, targets, '2024-02-01', '2024-02-05',
                                   initial_capital=1000, annual_cash_rate=.05)
    assert output['daily_ledger'].nav.iloc[-1] == pytest.approx(1000 * 1.05 ** (4 / 365.25))
    assert output['trades'].empty
    assert output['daily_holdings'].empty
    assert output['daily_ledger'].market_pnl.eq(0).all()


def test_common_window_uses_later_start_earlier_end_and_identical_dates():
    dates = pd.bdate_range('2024-01-01', '2024-07-02')
    prices = market(dates, [100.] * len(dates))
    month_ends = prices.groupby(prices.date.dt.to_period('M')).date.max().unique()[:-1]
    ranked = pd.DataFrame({'date': month_ends, 'ticker': 'A', 'rank': 1.})
    short = ranked.iloc[1:-1].copy()
    start, end = common_evaluation_window([ranked, short], prices)
    assert start == pd.Timestamp('2024-03-01')
    assert end == pd.Timestamp('2024-06-03')
    outputs = [run_top_n_backtest(frame, prices, evaluation_start=start, evaluation_end=end)
               for frame in [ranked, short]]
    pd.testing.assert_frame_equal(outputs[0]['daily_ledger'], outputs[1]['daily_ledger'])
    assert outputs[0]['returns'].index.equals(outputs[1]['returns'].index)
    with pytest.raises(ResearchDataError, match='gaps'):
        common_evaluation_window([ranked, short.drop(short.index[1])], prices)


def test_signal_date_exposures_and_actual_beta():
    holdings = pd.DataFrame({'date': pd.to_datetime(['2024-03-31']),
                             'signal_date': pd.to_datetime(['2024-03-28']),
                             'ticker': ['A'], 'weight': [1.]})
    features = pd.DataFrame({'date': pd.to_datetime(['2024-03-28']), 'ticker': ['A'],
                             'beta_252d': [1.2], 'beta_252d_z': [-.5]})
    result = compute_factor_exposures(holdings, features)
    assert result.exposure.iloc[0] == 1.2
    assert result.date.iloc[0] == pd.Timestamp('2024-03-31')


def test_dataset_roundtrip_and_tamper_detection(tmp_path):
    frame = pd.DataFrame({'date': pd.to_datetime(['2024-01-01', '2024-01-02']),
                          'ticker': ['NA', '001'], 'value': [np.pi, np.nan]})
    frame.attrs['historical_research_blocked'] = 'test restriction'
    path = save_dataset({'prices': frame}, tmp_path)
    loaded = load_dataset(path)['prices']
    pd.testing.assert_frame_equal(frame, loaded, check_exact=True)
    assert loaded.attrs == frame.attrs
    assert save_dataset({'prices': frame}, tmp_path) == path
    with (path / 'prices.csv').open('a') as handle:
        handle.write('changed')
    with pytest.raises(ResearchDataError, match='checksum'):
        load_dataset(path)


def test_run_replays_every_output_exactly(tmp_path):
    prices = market(['2024-01-31', '2024-02-01', '2024-02-02', '2024-02-05'], [100, 100, 90, 110])
    rankings = pd.DataFrame({'date': pd.to_datetime(['2024-01-31']), 'ticker': ['A'],
                             'rank': [1.], 'sector': ['Tech']})
    frames = {'prices': prices, 'rankings': rankings}
    result = run_top_n_backtest(rankings, prices, n=1)
    artifact = save_run(frames, result, {'n': 1}, tmp_path)
    replayed, second = replay_run(artifact['path'])
    assert artifact == second
    pd.testing.assert_frame_equal(result['daily_ledger'], replayed['daily_ledger'], check_exact=True)
    assert (tmp_path / 'runs' / artifact['run_id'] / 'outputs' / 'trades.csv').exists()
    manifest = json.loads((tmp_path / 'runs' / artifact['run_id'] / 'manifest.json').read_text())
    assert manifest['environment']['packages']['numpy']
