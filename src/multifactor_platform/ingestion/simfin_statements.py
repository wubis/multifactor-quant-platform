"""Convert standard quarterly SimFin bulk statements into revision-aware TTM states."""
from hashlib import sha256
import json

import numpy as np
import pandas as pd

from multifactor_platform.ingestion.free_sources import annotate_simfin_availability
from multifactor_platform.research import ResearchDataError


TABLE_FIELDS = {
    'income': ['Revenue', 'Gross Profit', 'Net Income'],
    'balance': ['Total Equity', 'Short Term Debt', 'Long Term Debt'],
    'cashflow': ['Net Cash from Operating Activities', 'Change in Fixed Assets & Intangibles'],
}
METADATA = ['SimFinId', 'Fiscal Year', 'Fiscal Period', 'Report Date', 'Publish Date',
            'Restated Date', 'Currency']


def validate_crosswalk(crosswalk):
    required = ['SimFinId', 'security_id', 'ticker', 'tiingo_symbol']
    if not set(required).issubset(crosswalk):
        raise ResearchDataError(f'Crosswalk requires {required}')
    result = crosswalk[required].copy()
    for column in required:
        if result[column].isna().any() or result[column].astype(str).str.strip().eq('').any():
            raise ResearchDataError(f'Missing crosswalk {column}')
        result[column] = result[column].astype(str)
        if result[column].duplicated().any():
            raise ResearchDataError('Crosswalk must map one primary security per SimFin company; aliases are not inferred')
    if result.empty:
        raise ResearchDataError('Empty security crosswalk')
    return result


def _quarterly_rows(table, name, ids, retrieved_at):
    required = METADATA + TABLE_FIELDS[name]
    if not set(required).issubset(table):
        raise ResearchDataError(f'{name}: missing columns {sorted(set(required) - set(table))}')
    rows = table[required].copy()
    rows['SimFinId'] = rows.SimFinId.astype(str)
    rows = rows.loc[rows.SimFinId.isin(ids)].copy()
    if set(rows.SimFinId) != ids:
        raise ResearchDataError(f'{name}: missing one or more explicitly requested SimFin IDs')
    if not rows.Currency.eq('USD').all() or not rows['Fiscal Period'].isin(['Q1', 'Q2', 'Q3', 'Q4']).all():
        raise ResearchDataError(f'{name}: requires USD, discrete-quarter bulk data (no annual, TTM or YTD rows)')
    years = pd.to_numeric(rows['Fiscal Year'], errors='raise')
    if not np.isfinite(years).all() or not years.eq(years.round()).all():
        raise ResearchDataError('Invalid fiscal years')
    rows['_quarter'] = years.astype(int) * 4 + rows['Fiscal Period'].str[-1].astype(int) - 1
    for field in TABLE_FIELDS[name]:
        rows[field] = pd.to_numeric(rows[field], errors='raise')
        if np.isinf(rows[field]).any():
            raise ResearchDataError(f'{name}: infinite {field}')
    rows = annotate_simfin_availability(rows, retrieved_at)
    keys = ['SimFinId', '_quarter', 'available_at']
    rows = rows.drop_duplicates()
    if rows.duplicated(keys).any():
        raise ResearchDataError(f'{name}: ambiguous same-quarter revision; retain explicit vintage timestamps')
    if rows.groupby(['SimFinId', '_quarter'])['Report Date'].nunique().gt(1).any():
        raise ResearchDataError(f'{name}: conflicting fiscal-period endpoints')
    for _, company in rows.groupby('SimFinId'):
        periods = company.drop_duplicates('_quarter').sort_values('_quarter')['Report Date']
        if not periods.is_monotonic_increasing or periods.duplicated().any():
            raise ResearchDataError(f'{name}: fiscal quarter order conflicts with report dates')
    rows['_table'] = name
    rows['_row_id'] = [sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()
                       for record in rows.to_dict('records')]
    return rows


def convert_simfin_quarterly(income, balance, cashflow, crosswalk, retrieved_at):
    """Recompute after each release, including late amendments to older quarters.

    Four consecutive flow quarters form TTM values; ROE uses opening/closing equity
    one year apart. Stability is negative population std of eight quarterly net
    margins. Missing/gapped histories produce no fabricated zero-filled snapshots.
    """
    mapping = validate_crosswalk(crosswalk).set_index('SimFinId')
    ids = set(mapping.index)
    tables = {name: _quarterly_rows(frame, name, ids, retrieved_at)
              for name, frame in [('income', income), ('balance', balance), ('cashflow', cashflow)]}
    events = pd.concat(tables.values(), ignore_index=True)
    rows, provenance = [], []
    skipped, last_signatures = 0, {}
    for simfin_id, company in events.groupby('SimFinId', sort=True):
        known = {name: {} for name in TABLE_FIELDS}
        for available_at, releases in company.sort_values('available_at').groupby('available_at', sort=True):
            for _, event in releases.iterrows():
                known[event['_table']][int(event['_quarter'])] = event
            common = set.intersection(*(set(table) for table in known.values()))
            if not common:
                skipped += 1
                continue
            quarter = max(common)
            needed = {'income': list(range(quarter - 7, quarter + 1)),
                      'cashflow': list(range(quarter - 3, quarter + 1)),
                      'balance': [quarter - 4, quarter]}
            if any(not set(qs).issubset(known[name]) for name, qs in needed.items()):
                skipped += 1
                continue
            used = [(name, known[name][q]) for name, qs in needed.items() for q in qs]
            if any(event[TABLE_FIELDS[name]].isna().any() for name, event in used):
                skipped += 1
                continue
            # All statements in a given quarter must refer to the same period end.
            endpoints = {}
            for _, event in used:
                endpoints.setdefault(event['_quarter'], set()).add(event['Report Date'])
            if any(len(values) > 1 for values in endpoints.values()):
                raise ResearchDataError('Statement tables disagree on fiscal period endpoints')
            quarters = [known['income'][q] for q in needed['income']]
            gaps = pd.Series([event['Report Date'] for event in quarters]).diff().dropna().dt.days
            if not gaps.between(60, 120).all():
                skipped += 1
                continue  # Fiscal-year transitions / nonstandard periods need a separate policy.
            revenue = np.array([event['Revenue'] for event in quarters], dtype=float)
            if (revenue <= 0).any():
                skipped += 1
                continue
            signature = tuple(sorted(event['_row_id'] for _, event in used))
            if signature == last_signatures.get(simfin_id):
                continue
            last_signatures[simfin_id] = signature
            revision = sha256('|'.join(signature).encode()).hexdigest()
            current = known['balance'][quarter]
            opening = known['balance'][quarter - 4]
            cash = [known['cashflow'][q] for q in needed['cashflow']]
            rows.append({
                'security_id': mapping.loc[simfin_id, 'security_id'],
                'fiscal_period_end': str(current['Report Date'].date()),
                'published_at': max(event['published_at'] for _, event in used).isoformat(),
                'available_at': available_at.isoformat(), 'revision_id': revision,
                'net_income_ttm': sum(event['Net Income'] for event in quarters[-4:]),
                'free_cash_flow_ttm': sum(event['Net Cash from Operating Activities'] +
                                         event['Change in Fixed Assets & Intangibles'] for event in cash),
                'book_equity': current['Total Equity'],
                'average_book_equity': (current['Total Equity'] + opening['Total Equity']) / 2,
                'gross_profit_ttm': sum(event['Gross Profit'] for event in quarters[-4:]),
                'revenue_ttm': sum(event['Revenue'] for event in quarters[-4:]),
                'total_debt': current['Short Term Debt'] + current['Long Term Debt'],
                'earnings_stability': -float(np.std(
                    np.array([event['Net Income'] for event in quarters], dtype=float) / revenue)),
                'source': 'simfin_free_quarterly_reconstructed',
                'retrieved_at': pd.Timestamp(retrieved_at).isoformat(),
            })
            for name, event in used:
                provenance.append({'revision_id': revision, 'table': name, 'row_id': event['_row_id'],
                                   'SimFinId': simfin_id, 'fiscal_quarter': int(event['_quarter']),
                                   'report_date': str(event['Report Date'].date()),
                                   'available_at': event['available_at'].isoformat()})
    if not rows:
        raise ResearchDataError('No complete eight-quarter histories; cannot produce the full factor contract')
    result = pd.DataFrame(rows).sort_values(['security_id', 'available_at']).reset_index(drop=True)
    return {'fundamentals': result, 'provenance': pd.DataFrame(provenance),
            'report': {'output_states': len(result), 'output_securities': int(result.security_id.nunique()),
                       'requested_securities': len(mapping), 'skipped_release_states': skipped,
                       'uncovered_security_ids': sorted(set(mapping.security_id) - set(result.security_id)),
                       'availability_basis': 'after later publication/restatement date; prior vintages may be absent',
                       'earnings_stability_definition': 'negative population std of eight consecutive quarterly net margins',
                       'fcf_definition': 'operating cash flow plus signed change in fixed assets & intangibles',
                       'roe_equity_definition': 'mean of opening and closing equity one fiscal year apart'}}
