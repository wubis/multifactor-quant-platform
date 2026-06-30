import pandas as pd


def equal_weight_top_n(ranked: pd.DataFrame, date, n: int = 50) -> pd.DataFrame:
    slice_ = ranked.loc[ranked["date"] == pd.Timestamp(date)].nsmallest(n, "rank").copy()
    if slice_.empty:
        return pd.DataFrame(columns=["date", "ticker", "weight"])
    slice_["weight"] = 1 / len(slice_)
    return slice_[["date", "ticker", "weight"]]


def calculate_turnover(current: pd.Series, previous: pd.Series | None) -> float:
    if previous is None:
        return float(current.abs().sum())
    aligned = pd.concat([current, previous], axis=1).fillna(0)
    aligned.columns = ["current", "previous"]
    return float((aligned["current"] - aligned["previous"]).abs().sum() / 2)
