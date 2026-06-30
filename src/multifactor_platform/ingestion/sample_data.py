import numpy as np
import pandas as pd

from multifactor_platform.ingestion.universe import load_default_universe


def make_sample_prices(days: int = 756, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    rows = []

    for idx, security in enumerate(load_default_universe()):
        drift = 0.0002 + idx * 0.00001
        vol = 0.012 + (idx % 5) * 0.002
        returns = rng.normal(drift, vol, size=len(dates))
        close = 100 * np.exp(np.cumsum(returns))
        volume = rng.integers(1_000_000, 12_000_000, size=len(dates))
        open_price = close * (1 + rng.normal(0, 0.002, size=len(dates)))
        high = np.maximum(open_price, close) * (1 + rng.uniform(0, 0.01, size=len(dates)))
        low = np.minimum(open_price, close) * (1 - rng.uniform(0, 0.01, size=len(dates)))

        rows.extend(
            {
                "date": date,
                "ticker": security.ticker,
                "sector": security.sector,
                "open": open_price[i],
                "high": high[i],
                "low": low[i],
                "close": close[i],
                "adj_close": close[i],
                "volume": float(volume[i]),
            }
            for i, date in enumerate(dates)
        )

    return pd.DataFrame(rows)


def make_sample_fundamentals(seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    as_of_dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=12, freq="QE")

    for security in load_default_universe():
        if security.ticker == "SPY":
            continue

        base_market_cap = rng.uniform(20e9, 3_000e9)
        for date in as_of_dates:
            rows.append(
                {
                    "date": date,
                    "ticker": security.ticker,
                    "pe_ratio": rng.uniform(8, 45),
                    "pb_ratio": rng.uniform(1, 15),
                    "ev_to_ebitda": rng.uniform(5, 30),
                    "fcf_yield": rng.uniform(0.005, 0.08),
                    "roe": rng.uniform(0.04, 0.45),
                    "gross_margin": rng.uniform(0.15, 0.85),
                    "debt_to_equity": rng.uniform(0.0, 2.5),
                    "earnings_stability": rng.uniform(0.2, 1.0),
                    "market_cap": base_market_cap * rng.uniform(0.85, 1.2),
                }
            )

    return pd.DataFrame(rows)
