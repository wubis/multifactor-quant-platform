import pandas as pd

from multifactor_platform.features.momentum import add_momentum_features


def test_momentum_uses_only_past_prices():
    dates = pd.bdate_range("2024-01-01", periods=30)
    prices = pd.DataFrame(
        {
            "date": dates,
            "ticker": "AAA",
            "open": range(100, 130),
            "high": range(101, 131),
            "low": range(99, 129),
            "close": range(100, 130),
            "adj_close": range(100, 130),
            "volume": 1_000_000,
        }
    )

    result = add_momentum_features(prices)
    day_22 = result.iloc[21]

    assert day_22["momentum_1m"] == (121 / 100) - 1
    assert pd.isna(result.iloc[20]["momentum_1m"])
