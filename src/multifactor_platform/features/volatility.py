import numpy as np
import pandas as pd


def add_volatility_features(prices: pd.DataFrame, benchmark_ticker: str = "SPY") -> pd.DataFrame:
    output = prices.sort_values(["ticker", "date"]).copy()
    output["daily_return"] = output.groupby("ticker")["adj_close"].pct_change()
    grouped_returns = output.groupby("ticker", group_keys=False)["daily_return"]
    output["volatility_20d"] = grouped_returns.rolling(20).std().reset_index(level=0, drop=True)
    output["volatility_60d"] = grouped_returns.rolling(60).std().reset_index(level=0, drop=True)

    benchmark = (
        output.loc[output["ticker"] == benchmark_ticker, ["date", "daily_return"]]
        .rename(columns={"daily_return": "benchmark_return"})
        .dropna()
    )
    output = output.merge(benchmark, on="date", how="left")

    def rolling_beta(frame: pd.DataFrame) -> pd.Series:
        covariance = frame["daily_return"].rolling(252).cov(frame["benchmark_return"])
        variance = frame["benchmark_return"].rolling(252).var()
        return covariance / variance.replace(0, np.nan)

    beta_parts = []
    for _, frame in output.groupby("ticker", sort=False):
        beta_parts.append(rolling_beta(frame))
    output["beta_252d"] = pd.concat(beta_parts).sort_index()
    return output
