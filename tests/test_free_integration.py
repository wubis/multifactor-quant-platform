from datetime import datetime, timezone
import json

import pandas as pd
import pytest

from multifactor_platform.ingestion.simfin_statements import convert_simfin_quarterly
from multifactor_platform.ingestion.tiingo_client import QuotaExceeded, TiingoClient
from multifactor_platform.research import ResearchDataError


def statements():
    dates = pd.date_range('2020-03-31', periods=8, freq='QE')
    base = pd.DataFrame([{
        'SimFinId': '1', 'Fiscal Year': date.year, 'Fiscal Period': f'Q{date.quarter}',
        'Report Date': str(date.date()),
        'Publish Date': str((date + pd.Timedelta(days=40)).date()),
        'Restated Date': str((date + pd.Timedelta(days=40)).date()), 'Currency': 'USD',
    } for date in dates])
    income = base.assign(Revenue=100, **{'Gross Profit': 50, 'Net Income': 10})
    balance = base.assign(**{'Total Equity': 200, 'Short Term Debt': 10, 'Long Term Debt': 20})
    cashflow = base.assign(**{'Net Cash from Operating Activities': 20,
                             'Change in Fixed Assets & Intangibles': -5})
    crosswalk = pd.DataFrame([{'SimFinId': '1', 'security_id': 's1', 'ticker': 'AAA',
                               'tiingo_symbol': 'AAA'}])
    return dict(income=income, balance=balance, cashflow=cashflow, crosswalk=crosswalk,
                retrieved_at='2023-01-01T00:00:00Z')


def test_ttm_and_late_amendment():
    inputs = statements()
    amendment = inputs['income'].iloc[[5]].copy()
    amendment['Net Income'] = 30
    amendment['Restated Date'] = '2022-06-01'
    inputs['income'] = pd.concat([inputs['income'], amendment], ignore_index=True)
    result = convert_simfin_quarterly(**inputs)
    rows = result['fundamentals']
    assert rows.net_income_ttm.tolist() == [40, 60]
    assert rows.free_cash_flow_ttm.tolist() == [60, 60]
    assert rows.average_book_equity.tolist() == [200, 200]
    assert rows.fiscal_period_end.nunique() == 1
    assert rows.iloc[1].available_at.startswith('2022-06-02')
    assert rows.revision_id.nunique() == 2
    assert len(result['provenance']) == 28


@pytest.mark.parametrize('problem', ['gap', 'missing', 'annual', 'currency'])
def test_incomplete_or_incompatible_statements_rejected(problem):
    inputs = statements()
    if problem == 'gap':
        inputs['income'] = inputs['income'].iloc[1:]
    elif problem == 'missing':
        inputs['income'].loc[7, 'Revenue'] = float('nan')
    elif problem == 'annual':
        inputs['income'].loc[7, 'Fiscal Period'] = 'FY'
    else:
        inputs['income'].loc[7, 'Currency'] = 'EUR'
    with pytest.raises(ResearchDataError):
        convert_simfin_quarterly(**inputs)


def body(close=10):
    return json.dumps([dict(date='2022-01-03T00:00:00Z', open=10, high=11, low=9,
                           close=close, adjClose=close, volume=100)]).encode()


def client(tmp_path, transport, **kwargs):
    return TiingoClient(token='secret-test-token', cache_dir=tmp_path, transport=transport,
                        clock=lambda: datetime(2022, 2, 1, tzinfo=timezone.utc), **kwargs)


def download(c, **kwargs):
    return c.download('AAA', '2022-01-01', '2022-01-31', **kwargs)


def test_cache_refresh_and_persistent_budget(tmp_path):
    calls = []
    def transport(url, cap):
        calls.append(url)
        return 200, body(len(calls) + 10)
    c = client(tmp_path, transport, limits={'requests_per_hour': 2})
    first = download(c)
    assert download(c)['cache_hit']
    second = download(c, refresh=True)
    assert first['sha256'] != second['sha256']
    assert len(list((tmp_path / 'responses').glob('*.json'))) == 2
    assert all('secret-test-token' not in url for url in calls)
    with pytest.raises(QuotaExceeded):
        download(client(tmp_path, transport, limits={'requests_per_hour': 2}), refresh=True)
    assert len(calls) == 2


def test_rate_limit_stops_without_retry(tmp_path):
    calls = []
    def transport(url, cap):
        calls.append(url)
        return 429, b''
    c = client(tmp_path, transport)
    with pytest.raises(ResearchDataError, match='HTTP 429'):
        download(c)
    with pytest.raises(QuotaExceeded):
        download(c)
    assert len(calls) == 1


@pytest.mark.parametrize('payload', [b'{}', b'[]', b'invalid', body() * 2])
def test_invalid_response_is_not_cached(tmp_path, payload):
    with pytest.raises(ResearchDataError):
        download(client(tmp_path, lambda url, cap: (200, payload)))
    assert not (tmp_path / 'responses').exists()


def test_bandwidth_and_symbol_caps(tmp_path):
    c = client(tmp_path, lambda url, cap: (200, body()),
               max_response_bytes=1000, limits={'unique_symbols_per_month': 1})
    download(c)
    with pytest.raises(QuotaExceeded, match='unique-symbol'):
        c.download('BBB', '2022-01-01', '2022-01-31')
    c = client(tmp_path / 'other', lambda url, cap: pytest.fail('must not request'),
               max_response_bytes=1000, limits={'bandwidth_bytes_per_month': 999})
    with pytest.raises(QuotaExceeded, match='bandwidth'):
        download(c)


def test_corrupt_cache_rejected(tmp_path):
    c = client(tmp_path, lambda url, cap: (200, body()))
    receipt = download(c)
    from pathlib import Path
    Path(receipt['path']).write_bytes(b'corrupted')
    with pytest.raises(ResearchDataError, match='checksum'):
        download(c)
