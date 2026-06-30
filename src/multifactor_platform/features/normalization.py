import numpy as np
import pandas as pd


def winsorize_series(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    if series.dropna().empty:
        return series
    return series.clip(series.quantile(lower), series.quantile(upper))


def zscore_series(series: pd.Series) -> pd.Series:
    std = series.std(ddof=0)
    if std == 0 or np.isnan(std):
        return series * 0
    return (series - series.mean()) / std


def normalize_cross_section(
    features: pd.DataFrame,
    columns: list[str],
    date_column: str = "date",
) -> pd.DataFrame:
    output = features.copy()
    for column in columns:
        output[f"{column}_z"] = output.groupby(date_column)[column].transform(
            lambda values: zscore_series(winsorize_series(values))
        )
        output[f"{column}_pct_rank"] = output.groupby(date_column)[column].rank(pct=True)
    return output


def latest_fundamentals_asof(prices: pd.DataFrame, fundamentals: pd.DataFrame) -> pd.DataFrame:
    joined = []
    for ticker, price_rows in prices.groupby("ticker", sort=False):
        fundamental_rows = (
            fundamentals.loc[fundamentals["ticker"] == ticker]
            .drop(columns=["ticker"])
            .sort_values("date")
        )
        if fundamental_rows.empty:
            joined.append(price_rows.copy())
            continue

        joined.append(
            pd.merge_asof(
                price_rows.sort_values("date"),
                fundamental_rows,
                on="date",
                direction="backward",
                allow_exact_matches=True,
            )
        )

    output = pd.concat(joined, ignore_index=True)
    return output.sort_values(["ticker", "date"]).reset_index(drop=True)
