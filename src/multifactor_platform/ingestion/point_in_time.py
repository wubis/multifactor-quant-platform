"""Validated, provider-independent historical research packets (USD US equities).

Fundamental rows are complete as-reported TTM/balance-sheet states, not individual
XBRL facts. Availability timestamps must come from a documented provider policy.
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

from multifactor_platform.artifacts import load_dataset, save_dataset
from multifactor_platform.features.momentum import add_momentum_features
from multifactor_platform.features.normalization import normalize_cross_section
from multifactor_platform.features.pipeline import FACTOR_COLUMNS
from multifactor_platform.features.volatility import add_volatility_features
from multifactor_platform.models.ml import MODEL_FEATURE_COLUMNS
from multifactor_platform.models.ranker import rank_stocks
from multifactor_platform.research import ResearchDataError


FINANCIAL_FIELDS = ['net_income_ttm', 'free_cash_flow_ttm', 'book_equity',
                    'average_book_equity', 'gross_profit_ttm', 'revenue_ttm',
                    'total_debt', 'earnings_stability']
COMMON = ['security_id', 'source', 'retrieved_at']
REQUIRED = {
    'prices': COMMON + ['ticker', 'date', 'decision_at', 'open', 'high', 'low', 'close',
                        'adj_close', 'volume', 'market_cap'],
    'fundamentals': COMMON + ['fiscal_period_end', 'published_at', 'available_at',
                              'revision_id'] + FINANCIAL_FIELDS,
    'membership': COMMON + ['effective_date', 'available_at', 'eligible', 'sector'],
}


def _timestamps(frame, column):
    text = frame[column].astype(str)
    if not text.str.contains(r'(?:Z|[+-]\d{2}:\d{2})$', regex=True).all():
        raise ResearchDataError(f'{column} requires explicit timezone offsets')
    frame[column] = pd.to_datetime(frame[column], utc=True, errors='raise', format='mixed')
    if frame[column].isna().any():
        raise ResearchDataError(f'{column} contains missing timestamps')


def _dates(frame, column):
    text = frame[column].astype(str)
    if not text.str.fullmatch(r'\d{4}-\d{2}-\d{2}').all():
        raise ResearchDataError(f'{column} must use YYYY-MM-DD dates')
    frame[column] = pd.to_datetime(text, errors='raise')


def validate_packet(frames, manifest):
    if manifest.get('schema_version') != 1 or manifest.get('currency') != 'USD':
        raise ResearchDataError('Requires schema_version 1 and USD accounting units')
    for key in ['provider', 'availability_policy', 'universe_policy', 'corporate_action_policy',
                'earnings_stability_definition']:
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ResearchDataError(f'Missing documented policy: {key}')
    output = {}
    for name, required in REQUIRED.items():
        frame = frames[name].copy()
        missing = set(required) - set(frame)
        if missing or frame.empty:
            raise ResearchDataError(f'{name}: empty data or missing columns {sorted(missing)}')
        # Select the contract columns; vendor-specific fields remain in the original export.
        frame = frame[required].copy()
        for column in ['security_id', 'source']:
            if frame[column].isna().any() or frame[column].astype(str).str.strip().eq('').any():
                raise ResearchDataError(f'{name}: missing {column}')
            frame[column] = frame[column].astype(str)
        _timestamps(frame, 'retrieved_at')
        if name == 'prices':
            _dates(frame, 'date')
            _timestamps(frame, 'decision_at')
            if frame.duplicated(['security_id', 'date']).any():
                raise ResearchDataError('Duplicate security/session prices')
            if frame.groupby('date').decision_at.nunique().gt(1).any():
                raise ResearchDataError('All securities must share the session decision timestamp')
            local_dates = frame.decision_at.dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize()
            if not frame.date.eq(local_dates).all():
                raise ResearchDataError('decision_at must belong to the US session date')
            if (frame.retrieved_at < frame.decision_at).any():
                raise ResearchDataError('Price retrieval precedes its decision timestamp')
            for column in ['open', 'high', 'low', 'close', 'adj_close', 'volume', 'market_cap']:
                frame[column] = pd.to_numeric(frame[column], errors='raise')
            values = frame[['open', 'high', 'low', 'close', 'adj_close']]
            if (~np.isfinite(values) | (values <= 0)).any().any():
                raise ResearchDataError('Prices must be finite and positive; do not invent missing marks')
            if (~np.isfinite(frame.volume) | (frame.volume < 0)).any():
                raise ResearchDataError('Volume must be finite and nonnegative')
            stocks = frame.loc[frame.ticker != 'SPY']
            if (~np.isfinite(stocks.market_cap) | (stocks.market_cap <= 0)).any():
                raise ResearchDataError('Historical daily market_cap is required for each stock')
        else:
            _timestamps(frame, 'available_at')
            if (frame.retrieved_at < frame.available_at).any():
                raise ResearchDataError(f'{name}: retrieval precedes availability')
            if name == 'fundamentals':
                _dates(frame, 'fiscal_period_end')
                _timestamps(frame, 'published_at')
                if ((frame.published_at > frame.available_at) |
                    (frame.fiscal_period_end.dt.tz_localize('UTC') > frame.published_at)).any():
                    raise ResearchDataError('Fundamental publication/availability chronology is invalid')
                if frame.revision_id.isna().any() or frame.revision_id.astype(str).str.strip().eq('').any():
                    raise ResearchDataError('Each fundamental revision requires an identity')
                if frame.duplicated(['security_id', 'fiscal_period_end', 'available_at']).any():
                    raise ResearchDataError('Ambiguous fundamental revisions at the same timestamp')
                for column in FINANCIAL_FIELDS:
                    frame[column] = pd.to_numeric(frame[column], errors='raise')
                    if np.isinf(frame[column]).any():
                        raise ResearchDataError(f'Infinite fundamental value: {column}')
            else:
                _dates(frame, 'effective_date')
                frame['eligible'] = frame.eligible.astype(str).str.lower().map({'true': True, 'false': False})
                if frame.eligible.isna().any():
                    raise ResearchDataError('Membership eligible must be true or false')
                if frame.sector.isna().any() or frame.sector.astype(str).str.strip().eq('').any():
                    raise ResearchDataError('Membership events require historical sector labels')
                if frame.duplicated(['security_id', 'effective_date', 'available_at']).any():
                    raise ResearchDataError('Ambiguous membership events')
        output[name] = frame
    prices = output['prices']
    if prices.ticker.isna().any() or prices.ticker.astype(str).str.strip().eq('').any():
        raise ResearchDataError('Missing ticker symbol')
    if prices.groupby('security_id').ticker.nunique().gt(1).any() or prices.groupby('ticker').security_id.nunique().gt(1).any():
        raise ResearchDataError('Symbol changes/reuse require a stable canonical symbol before import')
    if prices.loc[prices.ticker == 'SPY', 'security_id'].nunique() != 1:
        raise ResearchDataError('One SPY benchmark series is required')
    stocks = set(prices.loc[prices.ticker != 'SPY', 'security_id'])
    for name in ['fundamentals', 'membership']:
        if set(output[name].security_id) != stocks:
            raise ResearchDataError(f'{name}: IDs must cover exactly the supplied stock histories')
    return output


def import_packet(directory, archive_root='data/processed/research'):
    directory = Path(directory)
    try:
        manifest = json.loads((directory / 'manifest.json').read_text())
        frames = {name: pd.read_csv(directory / f'{name}.csv',
                                    dtype={'security_id': str, 'ticker': str, 'revision_id': str},
                                    keep_default_na=False, na_values=[''], float_precision='round_trip')
                  for name in REQUIRED}
        validated = validate_packet(frames, manifest)
    except (OSError, ValueError, KeyError) as exc:
        raise ResearchDataError(f'Invalid point-in-time packet: {exc}') from exc
    # Keep the declared policies with each immutable normalized input table.
    for frame in validated.values():
        frame.attrs['point_in_time_manifest'] = manifest
    path = save_dataset(validated, archive_root)
    return {'dataset_id': path.name, 'path': str(path.resolve()),
            'rows': {name: len(frame) for name, frame in validated.items()}}


def _join_states(prices, events, period_column, prefix):
    """Use only known events; an older-period correction cannot replace a newer state."""
    parts = []
    events = events.copy()
    events['_usable_at'] = events.available_at
    if period_column == 'effective_date':
        events['_usable_at'] = pd.concat([
            events.available_at, events.effective_date.dt.tz_localize('UTC')], axis=1).max(axis=1)
    for security_id, rows in prices.groupby('security_id', sort=False):
        history = events.loc[events.security_id == security_id].sort_values(['_usable_at', period_column])
        chosen, latest_period = [], None
        for _, event in history.iterrows():
            period = event[period_column]
            if latest_period is None or period >= latest_period:
                chosen.append(event)
                latest_period = period
        if not chosen:
            continue
        states = pd.DataFrame(chosen).drop_duplicates('_usable_at', keep='last')
        states = states.drop(columns=['security_id']).rename(
            columns={column: f'{prefix}_{column}' for column in states if column != 'security_id'})
        parts.append(pd.merge_asof(rows.sort_values('decision_at'), states,
                                    left_on='decision_at', right_on=f'{prefix}__usable_at',
                                    direction='backward', allow_exact_matches=True))
    if not parts:
        raise ResearchDataError('No historical states match price security IDs')
    return pd.concat(parts, ignore_index=True)


def build_point_in_time_data(snapshot_path):
    frames = load_dataset(snapshot_path)
    prices, fundamentals, membership = (frames[name].copy() for name in REQUIRED)
    manifest = prices.attrs.get('point_in_time_manifest')
    if not manifest:
        raise ResearchDataError('Snapshot is not a validated point-in-time packet')
    # All return lookbacks are computed before the universe filter.
    features = add_volatility_features(add_momentum_features(prices))
    # Compute targets on the full benchmark calendar before exits/entries remove rows.
    calendar = pd.DatetimeIndex(prices.loc[prices.ticker == 'SPY', 'date'].sort_values().unique())
    end_dates = pd.Series(calendar, index=calendar).shift(-21)
    features['forward_end_21d'] = features.date.map(end_dates)
    future = prices[['ticker', 'date', 'adj_close']].rename(
        columns={'date': 'forward_end_21d', 'adj_close': 'forward_price_21d'})
    features = features.merge(future, on=['ticker', 'forward_end_21d'], how='left', validate='many_to_one')
    features = features.loc[features.ticker != 'SPY'].copy()
    features = _join_states(features, membership, 'effective_date', 'membership')
    known_members = features.membership_eligible.eq(True)
    eligible = features.loc[known_members].copy()
    if eligible.empty:
        raise ResearchDataError('No eligible observations under the historical membership events')
    eligible['sector'] = eligible['membership_sector']
    eligible = _join_states(eligible, fundamentals, 'fiscal_period_end', 'fundamental')
    fresh = (eligible.date - eligible.fundamental_fiscal_period_end).dt.days.between(0, 550)
    eligible = eligible.loc[fresh].copy()
    def f(column):
        return eligible[f'fundamental_{column}']
    eligible['pe_ratio'] = eligible.market_cap / f('net_income_ttm').where(f('net_income_ttm') > 0)
    eligible['pb_ratio'] = eligible.market_cap / f('book_equity').where(f('book_equity') > 0)
    eligible['fcf_yield'] = f('free_cash_flow_ttm') / eligible.market_cap
    eligible['roe'] = f('net_income_ttm') / f('average_book_equity').where(f('average_book_equity') > 0)
    eligible['gross_margin'] = f('gross_profit_ttm') / f('revenue_ttm').where(f('revenue_ttm') > 0)
    eligible['debt_to_equity'] = f('total_debt') / f('book_equity').where(f('book_equity') > 0)
    eligible['earnings_stability'] = f('earnings_stability')
    eligible['dollar_volume'] = eligible.close * eligible.volume
    # Missing ratios are excluded, never imputed from future or ineligible stocks.
    eligible = eligible.replace([np.inf, -np.inf], np.nan).dropna(subset=FACTOR_COLUMNS)
    if eligible.empty:
        raise ResearchDataError('No complete observations after warmup, availability, and factor checks')
    eligible = normalize_cross_section(eligible, FACTOR_COLUMNS)
    eligible = eligible.dropna(subset=MODEL_FEATURE_COLUMNS).sort_values(['ticker', 'date']).reset_index(drop=True)
    rankings = rank_stocks(eligible)
    audit = {
        'point_in_time_dataset_id': Path(snapshot_path).name,
        'point_in_time_manifest': manifest,
        'point_in_time_validation': 'schema and temporal checks passed; provider accuracy is not certified',
        'eligible_rows_before_fundamentals': int(known_members.sum()),
        'complete_feature_rows': len(eligible),
        'excluded_feature_rows': int(known_members.sum()) - len(eligible),
    }
    for frame in [prices, eligible, rankings]:
        frame.attrs.update(audit)
    return prices, eligible, rankings
