import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from multifactor_platform.api.main import app
from multifactor_platform.backtesting.engine import _asset_returns, run_top_n_backtest
from multifactor_platform.backtesting.metrics import information_ratio, max_drawdown, sharpe_ratio
from multifactor_platform.models.ml import (
    LABEL_END_COLUMN, ModelSpec, add_forward_return_target, placebo_predictions,
    prepare_model_frame, walk_forward_validate_model,
)
from multifactor_platform.optimization.constraints import PortfolioConstraints
from multifactor_platform.optimization.optimizer import optimize_ranked_portfolio
from multifactor_platform.research import ResearchDataError
from multifactor_platform.utils import platform_data


def test_drawdown_includes_initial_capital():
    assert max_drawdown(pd.Series([-.1, .05])) == pytest.approx(-.1)
    assert max_drawdown(pd.Series([-.2])) == pytest.approx(-.2)
    assert max_drawdown(pd.Series(dtype=float)) == 0


def test_ratios_use_arithmetic_excess_returns():
    returns = pd.Series([.1, -.05, .02])
    expected = (returns - .001).mean() / returns.std(ddof=0) * np.sqrt(12)
    assert sharpe_ratio(returns, risk_free_return=.001) == pytest.approx(expected)
    assert information_ratio(returns) == pytest.approx(
        returns.mean() / returns.std(ddof=0) * np.sqrt(12)
    )


def test_forward_labels_do_not_cross_tickers_and_record_realization():
    frame = pd.DataFrame({
        'ticker': ['A'] * 3 + ['B'] * 3,
        'date': list(pd.date_range('2024-01-01', periods=3)) * 2,
        'adj_close': [10, 20, 40, 100, 90, 81],
    })
    result = add_forward_return_target(frame, horizon_days=1)
    assert result.loc[0, 'next_21d_return'] == 1
    assert result.loc[3, 'next_21d_return'] == pytest.approx(-.1)
    assert result.loc[[2, 5], 'next_21d_return'].isna().all()
    assert result.loc[0, LABEL_END_COLUMN] == pd.Timestamp('2024-01-02')


def test_training_cannot_observe_unrealized_labels():
    dates = pd.bdate_range('2020-01-01', periods=400)
    frame = pd.DataFrame({
        'date': dates, 'ticker': 'A', 'momentum_1m_z': np.arange(400),
        'next_21d_relative_return': np.arange(400) / 1000,
        LABEL_END_COLUMN: pd.Series(dates).shift(-21),
    }).dropna()
    seen = []

    class Recorder:
        def fit(self, x, y):
            seen.append(x.index)
            return self

        def predict(self, x):
            return x.iloc[:, 0].to_numpy() / 1000

    result = walk_forward_validate_model(frame, ModelSpec('record', Recorder, 'test'))
    assert seen
    for indices, fold in zip(seen, result['folds'].to_dict('records')):
        assert (frame.loc[indices, LABEL_END_COLUMN] < fold['validation_start']).all()
        assert fold['train_label_end'] < fold['validation_start']


def test_placebo_shuffles_within_dates_even_for_ticker_sorted_rows():
    frame = pd.DataFrame({'date': [1, 2, 1, 2], 'prediction': [10, 100, 20, 200]})
    shuffled = placebo_predictions(frame)
    for date in [1, 2]:
        assert set(shuffled.loc[shuffled.date == date, 'prediction']) == set(
            frame.loc[frame.date == date, 'prediction']
        )


def test_missing_execution_price_is_an_error():
    frame = pd.DataFrame({'date': pd.to_datetime(['2024-01-01']),
                          'ticker': ['A'], 'adj_close': [100.]})
    with pytest.raises(ValueError, match='Missing or invalid'):
        _asset_returns(frame, ['A'], pd.Timestamp('2024-01-01'), pd.Timestamp('2024-02-01'))


def test_drift_rebalancing_and_costs_reconcile():
    signals = pd.to_datetime(['2024-01-31', '2024-02-29', '2024-03-29'])
    ranked = pd.DataFrame([{'date': date, 'ticker': ticker, 'rank': rank}
                          for date in signals for ticker, rank in [('A', 1), ('B', 2)]])
    dates = pd.to_datetime(['2024-02-01', '2024-03-01', '2024-04-01'])
    prices = pd.DataFrame([{'date': date, 'ticker': ticker, 'adj_close': price}
                           for ticker, values in [('A', [100, 200, 200]),
                                                  ('B', [100, 100, 100]),
                                                  ('SPY', [100, 100, 100])]
                           for date, price in zip(dates, values)])
    result = run_top_n_backtest(ranked, prices, n=2, cost_bps=100)
    assert result['turnover'].iloc[1] == pytest.approx(1 / 6)
    # Initial buy costs 1% of the actual purchased notional, leaving 1 / 1.01 invested.
    assert result['returns'].iloc[0] == pytest.approx(1.5 / 1.01 - 1)
    # Rebalance from 2/3 A, 1/3 B: buying + selling is 1/3 NAV.
    assert result['costs'].total_cost.iloc[1] == pytest.approx(.01 / 3)
    assert result['returns'].iloc[1] == pytest.approx(-.01 / 3)


def test_optimizer_retains_old_holdings_to_limit_turnover():
    ranked = pd.DataFrame({'ticker': ['NEW', 'OLD'], 'sector': ['Tech', 'Tech'],
                           'rank': [1, 2], 'composite_score': [2., 1.]})
    result = optimize_ranked_portfolio(
        ranked, PortfolioConstraints(max_position_size=1, max_sector_exposure=1,
                                     max_turnover=.1, cash_minimum=0),
        previous_weights=pd.Series({'OLD': 1.}),
    )
    weights = result['positions'].set_index('ticker').weight
    assert weights['OLD'] == pytest.approx(.9)
    assert weights['NEW'] == pytest.approx(.1)
    assert result['turnover'] == pytest.approx(.1)


def test_future_fundamentals_do_not_supply_past_imputation():
    frame = pd.DataFrame({'date': pd.to_datetime(['2020-01-01', '2021-01-01']),
                          'ticker': ['A', 'A'], 'pe_ratio': [np.nan, 10.]})
    result = platform_data._fill_missing_fundamentals(frame)
    assert pd.isna(result.pe_ratio.iloc[0])


def test_yfinance_snapshot_date_is_preserved_and_research_blocked(monkeypatch):
    captured = {}
    prices = pd.DataFrame({'date': pd.to_datetime(['2020-01-01'])})
    fundamentals = pd.DataFrame({'date': pd.to_datetime(['2024-01-01'])})
    monkeypatch.setattr(platform_data, 'fetch_yfinance_prices', lambda **kw: prices)
    monkeypatch.setattr(platform_data, 'fetch_yfinance_fundamentals', lambda **kw: fundamentals)

    def finalize(p, f):
        captured['date'] = f.date.iloc[0]
        return p.copy(), pd.DataFrame(), pd.DataFrame()

    monkeypatch.setattr(platform_data, '_finalize_pipeline', finalize)
    output = platform_data.load_yfinance_platform_data.__wrapped__()
    assert captured['date'] == pd.Timestamp('2024-01-01')
    with pytest.raises(ResearchDataError, match='point-in-time'):
        prepare_model_frame(output[1])
    with pytest.raises(ResearchDataError, match='point-in-time'):
        run_top_n_backtest(output[2], output[0])


def test_api_explains_research_data_block(monkeypatch):
    import multifactor_platform.api.main as api
    frame = pd.DataFrame()
    frame.attrs['historical_research_blocked'] = 'Point-in-time fundamentals required'
    monkeypatch.setattr(api, '_load_data_or_503', lambda source: (frame, frame, frame))
    response = TestClient(app).get('/models?source=yfinance')
    assert response.status_code == 422
    assert 'Point-in-time' in response.json()['detail']


def test_optimizer_rejects_constraint_violating_transition():
    ranked = pd.DataFrame({'ticker': ['NEW', 'OLD'], 'sector': ['Tech', 'Health'],
                           'rank': [1, 2], 'composite_score': [2., 1.]})
    with pytest.raises(ValueError, match='violates portfolio constraints'):
        optimize_ranked_portfolio(
            ranked, PortfolioConstraints(max_position_size=.5, max_sector_exposure=1,
                                         max_turnover=.1, cash_minimum=0),
            previous_weights=pd.Series({'OLD': 1.}),
        )


def test_future_only_fundamentals_produce_no_historical_rankings():
    from multifactor_platform.ingestion.sample_data import make_sample_fundamentals, make_sample_prices
    prices = make_sample_prices(days=360)
    fundamentals = make_sample_fundamentals()
    fundamentals['date'] = prices.date.max() + pd.Timedelta(days=1)
    _, features, rankings = platform_data._finalize_pipeline(prices, fundamentals)
    assert features.empty
    assert rankings.empty


@pytest.mark.parametrize('endpoint', ['/rankings/latest', '/portfolio/latest', '/portfolio/optimized'])
def test_empty_rankings_have_explicit_api_response(monkeypatch, endpoint):
    import multifactor_platform.api.main as api
    frame = pd.DataFrame()
    monkeypatch.setattr(api, '_load_data_or_503', lambda source: (frame, frame, frame))
    response = TestClient(app).get(endpoint + '?source=yfinance')
    assert response.status_code == 422
    assert 'No eligible rankings' in response.json()['detail']
