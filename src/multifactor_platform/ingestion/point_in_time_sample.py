"""Fictitious data for exercising the import contract, never investment evidence."""
from pathlib import Path
import json

import numpy as np
import pandas as pd


def example_packet():
    dates = pd.bdate_range('2020-01-01', periods=420)
    decisions = (dates + pd.Timedelta(hours=16)).tz_localize('America/New_York').tz_convert('UTC')
    prices, fundamentals, membership = [], [], []
    retrieved = '2025-01-01T00:00:00Z'
    for j, ticker in enumerate(['AAA', 'BBB', 'SPY']):
        for i, (date, decision) in enumerate(zip(dates, decisions)):
            price = 100 * np.exp(.0002 * i + .015 * np.sin(i / (7 + j)))
            prices.append(dict(security_id=f'id-{ticker}', ticker=ticker, date=str(date.date()),
                               decision_at=decision.isoformat(), open=price, high=price * 1.01,
                               low=price * .99, close=price, adj_close=price, volume=1_000_000,
                               market_cap=price * 10_000_000, source='synthetic', retrieved_at=retrieved))
        if ticker == 'SPY':
            continue
        membership.append(dict(security_id=f'id-{ticker}', effective_date='2020-01-01',
                               available_at='2019-12-31T21:00:00Z', eligible=True,
                               sector=['Technology', 'Industrials'][j], source='synthetic', retrieved_at=retrieved))
        for q, period in enumerate(pd.date_range('2019-12-31', periods=6, freq='QE')):
            available = (period + pd.Timedelta(days=40, hours=22)).tz_localize('UTC').isoformat()
            fundamentals.append(dict(security_id=f'id-{ticker}', fiscal_period_end=str(period.date()),
                                     published_at=available, available_at=available, revision_id=f'{ticker}-{q}',
                                     net_income_ttm=100_000_000 + 1_000_000 * q + j * 20_000_000,
                                     free_cash_flow_ttm=90_000_000, book_equity=500_000_000,
                                     average_book_equity=450_000_000, gross_profit_ttm=400_000_000,
                                     revenue_ttm=1_000_000_000, total_debt=100_000_000,
                                     earnings_stability=.7 + j * .1, source='synthetic', retrieved_at=retrieved))
    manifest = dict(schema_version=1, currency='USD', provider='SYNTHETIC TEST FIXTURE',
                    availability_policy='Fictitious timestamps to test temporal gating; not market data.',
                    universe_policy='Two fictional stocks; not a real historical universe.',
                    corporate_action_policy='No corporate actions in this synthetic series.',
                    earnings_stability_definition='Synthetic values solely for software testing.')
    return {'prices': pd.DataFrame(prices), 'fundamentals': pd.DataFrame(fundamentals),
            'membership': pd.DataFrame(membership)}, manifest


def write_example(directory):
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=False)
    frames, manifest = example_packet()
    for name, frame in frames.items():
        frame.to_csv(path / f'{name}.csv', index=False, float_format='%.17g')
    (path / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    return path
