import json

import pandas as pd
import pytest

from multifactor_platform.artifacts import replay_run, save_run
from multifactor_platform.backtesting.engine import run_top_n_backtest
from multifactor_platform.ingestion.point_in_time import (
    _join_states, build_point_in_time_data, import_packet, validate_packet,
)
from multifactor_platform.ingestion.point_in_time_sample import example_packet, write_example
from multifactor_platform.models.ml import add_forward_return_target
from multifactor_platform.research import ResearchDataError


def save_packet(tmp_path, frames, manifest, name='packet'):
    path = tmp_path / name
    path.mkdir()
    for table, frame in frames.items():
        frame.to_csv(path / f'{table}.csv', index=False, float_format='%.17g')
    (path / 'manifest.json').write_text(json.dumps(manifest))
    return import_packet(path, tmp_path / 'archive')['path']


def test_availability_not_fiscal_period_controls_join_and_old_revisions_do_not_regress():
    prices = pd.DataFrame({'security_id': ['A'] * 4,
                           'decision_at': pd.to_datetime(['2024-04-01T20:00:00Z', '2024-04-02T20:00:00Z',
                                                          '2024-05-02T20:00:00Z', '2024-06-02T20:00:00Z'])})
    events = pd.DataFrame({'security_id': ['A'] * 3,
                           'available_at': pd.to_datetime(['2024-04-01T21:00:00Z', '2024-05-01T20:00:00Z',
                                                          '2024-06-01T20:00:00Z']),
                           'fiscal_period_end': pd.to_datetime(['2023-12-31', '2024-03-31', '2023-12-31']),
                           'value': [1, 2, 999]})
    result = _join_states(prices, events, 'fiscal_period_end', 'fundamental')
    assert pd.isna(result.fundamental_value.iloc[0])
    assert result.fundamental_value.iloc[1:].tolist() == [1, 2, 2]


def test_membership_requires_effective_date_and_known_availability():
    prices = pd.DataFrame({'security_id': ['A'] * 3,
                           'decision_at': pd.to_datetime(['2024-01-02T21:00:00Z', '2024-02-02T21:00:00Z',
                                                          '2024-03-02T21:00:00Z'])})
    events = pd.DataFrame({'security_id': ['A', 'A'],
                           'effective_date': pd.to_datetime(['2024-02-01', '2024-02-15']),
                           'available_at': pd.to_datetime(['2024-01-01T21:00:00Z', '2024-03-01T21:00:00Z']),
                           'eligible': [True, False]})
    result = _join_states(prices, events, 'effective_date', 'membership')
    assert pd.isna(result.membership_eligible.iloc[0])
    assert result.membership_eligible.iloc[1:].tolist() == [True, False]


@pytest.mark.parametrize('mutation,match', [
    ('naive', 'timezone'), ('publication', 'chronology'), ('revision', 'Ambiguous'),
    ('coverage', 'cover exactly'), ('symbol_reuse', 'Symbol changes'),
])
def test_invalid_packets_fail_closed(mutation, match):
    frames, manifest = example_packet()
    if mutation == 'naive':
        frames['fundamentals'].loc[0, 'available_at'] = '2020-02-09 22:00:00'
    elif mutation == 'publication':
        frames['fundamentals'].loc[0, 'published_at'] = '2024-01-01T00:00:00Z'
    elif mutation == 'revision':
        frames['fundamentals'] = pd.concat([frames['fundamentals'], frames['fundamentals'].iloc[[0]]])
    elif mutation == 'coverage':
        frames['membership'] = frames['membership'].iloc[:1]
    else:
        frames['prices'].loc[0, 'ticker'] = 'REUSED'
    with pytest.raises(ResearchDataError, match=match):
        validate_packet(frames, manifest)


def test_valuation_updates_with_daily_market_cap_and_no_future_restatement(tmp_path):
    frames, manifest = example_packet()
    original_path = save_packet(tmp_path, frames, manifest)
    _, original, _ = build_point_in_time_data(original_path)
    row = original.loc[original.ticker == 'AAA'].iloc[-5]
    assert row.pe_ratio == pytest.approx(row.market_cap / row.fundamental_net_income_ttm)
    revision = frames['fundamentals'].iloc[[0]].copy()
    revision['fiscal_period_end'] = '2021-03-31'
    revision['available_at'] = revision['published_at'] = '2021-07-01T22:00:00Z'
    revision['revision_id'] = 'revision-later'
    revision['net_income_ttm'] = 1.
    frames['fundamentals'] = pd.concat([frames['fundamentals'], revision], ignore_index=True)
    _, updated, _ = build_point_in_time_data(save_packet(tmp_path, frames, manifest, 'updated'))
    columns = ['date', 'ticker', 'pe_ratio', 'pe_ratio_z']
    pd.testing.assert_frame_equal(original.loc[original.date <= '2021-07-01', columns].reset_index(drop=True),
                                  updated.loc[updated.date <= '2021-07-01', columns].reset_index(drop=True))
    late = updated.loc[(updated.date > '2021-07-01') & (updated.ticker == 'AAA')]
    assert late.pe_ratio.max() > 1e8


def test_universe_exclusion_precedes_normalization_and_preserves_targets_after_exit(tmp_path):
    frames, manifest = example_packet()
    exit_event = frames['membership'].iloc[[1]].copy()
    exit_event['effective_date'] = '2021-05-03'
    exit_event['available_at'] = '2021-04-30T21:00:00Z'
    exit_event['eligible'] = False
    frames['membership'] = pd.concat([frames['membership'], exit_event], ignore_index=True)
    prices, features, _ = build_point_in_time_data(save_packet(tmp_path, frames, manifest))
    after = features.loc[features.date >= '2021-05-03']
    assert set(after.ticker) == {'AAA'}
    assert after.pe_ratio_z.eq(0).all()
    assert set(prices.ticker) == {'AAA', 'BBB', 'SPY'}
    targets = add_forward_return_target(features)
    before_exit = targets.loc[(targets.ticker == 'BBB') & (targets.date == '2021-04-30')].iloc[0]
    assert before_exit.forward_end_21d > pd.Timestamp('2021-05-03')
    assert pd.notna(before_exit.next_21d_return)
    endpoint = prices.loc[(prices.ticker == 'BBB') & (prices.date == before_exit.forward_end_21d)].adj_close.iloc[0]
    assert before_exit.next_21d_return == pytest.approx(endpoint / before_exit.adj_close - 1)


def test_point_in_time_backtest_replays_exactly(tmp_path):
    write_example(tmp_path / 'example')
    imported = import_packet(tmp_path / 'example', tmp_path / 'archive')
    prices, features, rankings = build_point_in_time_data(imported['path'])
    assert (features.fundamental_available_at <= features.decision_at).all()
    assert (features.membership_available_at <= features.decision_at).all()
    result = run_top_n_backtest(rankings, prices, features=features, n=2)
    artifact = save_run({'prices': prices, 'features': features, 'rankings': rankings}, result,
                        {'n': 2}, tmp_path / 'runs')
    replayed, identity = replay_run(artifact['path'])
    assert artifact == identity
    pd.testing.assert_frame_equal(result['daily_ledger'], replayed['daily_ledger'], check_exact=True)


def test_simfin_latest_restatement_is_not_backdated_to_original_publication():
    from multifactor_platform.ingestion.free_sources import annotate_simfin_availability
    raw = pd.DataFrame({'SimFinId': [1], 'Report Date': ['2020-12-31'],
                         'Publish Date': ['2021-02-01'], 'Restated Date': ['2022-03-13'],
                         'Net Income': [999.]})
    result = annotate_simfin_availability(raw, '2025-01-01T00:00:00Z')
    # March 14 is after the US spring DST transition: midnight is 04:00 UTC.
    assert result.available_at.iloc[0] == pd.Timestamp('2022-03-14T04:00:00Z')
    assert result['Net Income'].iloc[0] == 999
    raw['Restated Date'] = None
    with pytest.raises(ResearchDataError, match='Restated Date'):
        annotate_simfin_availability(raw, '2025-01-01T00:00:00Z')


def test_tiingo_adapter_requires_market_cap_and_preserves_raw_vs_adjusted_prices():
    from multifactor_platform.ingestion.free_sources import normalize_tiingo_eod
    raw = pd.DataFrame({'date': ['2020-01-02T00:00:00Z'], 'open': [100.], 'high': [101.],
                         'low': [99.], 'close': [100.], 'adjClose': [50.], 'volume': [1000.]})
    metadata = pd.DataFrame({'date': ['2020-01-02'], 'decision_at': ['2020-01-02T21:00:00Z'],
                             'market_cap': [1e9]})
    result = normalize_tiingo_eod(raw, '1', 'AAA', metadata, '2025-01-01T00:00:00Z')
    assert result.close.iloc[0] == 100
    assert result.adj_close.iloc[0] == 50
    assert result.market_cap.iloc[0] == 1e9
    with pytest.raises(ResearchDataError, match='independently'):
        normalize_tiingo_eod(raw, '1', 'AAA', metadata.drop(columns=['market_cap']), '2025-01-01T00:00:00Z')


def test_configured_missing_snapshot_returns_actionable_error(monkeypatch, tmp_path):
    from multifactor_platform.config import get_settings
    from multifactor_platform.utils.platform_data import load_platform_data
    monkeypatch.setattr(get_settings(), 'point_in_time_dataset', str(tmp_path / 'missing'))
    with pytest.raises(ResearchDataError, match='dataset unavailable'):
        load_platform_data('point_in_time')
