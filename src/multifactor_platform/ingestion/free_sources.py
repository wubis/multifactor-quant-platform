"""Boundary adapters for the selected free SimFin + Tiingo research stack.

These functions normalize locally downloaded records. They make no network calls,
subscribe to no services, and never infer a security crosswalk or missing shares.
"""
import pandas as pd

from multifactor_platform.research import ResearchDataError


TIINGO_FREE_LIMITS = {'unique_symbols_per_month': 500, 'requests_per_hour': 50,
                     'requests_per_day': 1000, 'bandwidth_bytes_per_month': 1_000_000_000}


def annotate_simfin_availability(statements: pd.DataFrame, retrieved_at: str) -> pd.DataFrame:
    """Annotate bulk statement rows without inventing a lost as-reported vintage.

    Date-only disclosures become eligible AFTER the later publication/restatement
    day in New York. This is a conservative reconstructed public-availability proxy,
    not a record of when the free vendor feed actually delivered the row.
    """
    required = {'SimFinId', 'Report Date', 'Publish Date', 'Restated Date'}
    if not required.issubset(statements):
        raise ResearchDataError(f'Missing SimFin columns: {sorted(required - set(statements))}')
    output = statements.copy()
    for column in ['Report Date', 'Publish Date', 'Restated Date']:
        values = output[column].astype(str)
        if not values.str.fullmatch(r'\d{4}-\d{2}-\d{2}').all():
            raise ResearchDataError(f'SimFin {column} must be present and date-only')
        output[column] = pd.to_datetime(values, errors='raise')
    if (output['Report Date'] > output['Publish Date']).any():
        raise ResearchDataError('SimFin report date follows publication date')
    latest = output[['Publish Date', 'Restated Date']].max(axis=1)
    # Add a calendar day before localization so DST shifts do not move midnight.
    output['available_at'] = (latest + pd.Timedelta(days=1)).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
    output['published_at'] = output['Publish Date'].dt.tz_localize('America/New_York').dt.tz_convert('UTC')
    retrieval = pd.Timestamp(retrieved_at)
    if retrieval.tzinfo is None:
        raise ResearchDataError('retrieved_at requires a timezone')
    if (output.available_at > retrieval).any():
        raise ResearchDataError('SimFin availability is later than retrieval')
    output['retrieved_at'] = retrieval.tz_convert('UTC')
    output.attrs['availability_basis'] = 'reconstructed_after_later_publication_or_restatement_day'
    output.attrs['vintage_limitations'] = (
        'Latest-restated bulk values do not recover prior reported values or historical vendor delivery times.'
    )
    return output


def normalize_tiingo_eod(records: pd.DataFrame, security_id: str, ticker: str,
                         session_metadata: pd.DataFrame, retrieved_at: str) -> pd.DataFrame:
    """Map Tiingo EOD fields; require independently sourced daily market cap/cutoffs.

    session_metadata: date, decision_at, market_cap. Raw close/volume must not be
    multiplied by split-adjusted statement shares to fabricate market capitalization.
    """
    required = {'date', 'open', 'high', 'low', 'close', 'adjClose', 'volume'}
    if not required.issubset(records):
        raise ResearchDataError(f'Missing Tiingo fields: {sorted(required - set(records))}')
    if not {'date', 'decision_at', 'market_cap'}.issubset(session_metadata):
        raise ResearchDataError('Daily market cap and decision timestamps must be supplied independently')
    output = records[list(required)].copy().rename(columns={'adjClose': 'adj_close'})
    # Tiingo's date is the session label encoded at UTC midnight, not a filing timestamp.
    output['date'] = pd.to_datetime(output.date, utc=True).dt.tz_localize(None).dt.normalize()
    metadata = session_metadata[['date', 'decision_at', 'market_cap']].copy()
    metadata['date'] = pd.to_datetime(metadata.date).dt.normalize()
    output = output.merge(metadata, on='date', how='left', validate='one_to_one')
    if output.decision_at.isna().any() or (ticker != 'SPY' and output.market_cap.isna().any()):
        raise ResearchDataError('Missing session metadata for Tiingo prices')
    output['date'] = output.date.dt.strftime('%Y-%m-%d')
    output['security_id'], output['ticker'] = str(security_id), ticker
    output['source'], output['retrieved_at'] = 'tiingo_eod', retrieved_at
    return output
