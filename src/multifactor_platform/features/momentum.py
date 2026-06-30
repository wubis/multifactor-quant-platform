import pandas as pd


TRADING_DAYS_PER_MONTH = 21


def add_momentum_features(prices: pd.DataFrame) -> pd.DataFrame:
    output = prices.sort_values(["ticker", "date"]).copy()
    grouped = output.groupby("ticker", group_keys=False)["adj_close"]
    output["momentum_1m"] = grouped.pct_change(TRADING_DAYS_PER_MONTH)
    output["momentum_3m"] = grouped.pct_change(3 * TRADING_DAYS_PER_MONTH)
    output["momentum_6m"] = grouped.pct_change(6 * TRADING_DAYS_PER_MONTH)
    output["momentum_12m_ex_1m"] = (
        grouped.shift(TRADING_DAYS_PER_MONTH).div(grouped.shift(12 * TRADING_DAYS_PER_MONTH)) - 1
    )
    return output
