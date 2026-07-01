import pandas as pd


def equal_weight_top_n(ranked: pd.DataFrame, date, n: int = 50) -> pd.DataFrame:
    slice_ = ranked.loc[ranked["date"] == pd.Timestamp(date)].nsmallest(n, "rank").copy()
    if slice_.empty:
        return pd.DataFrame(columns=["date", "ticker", "weight"])
    slice_["weight"] = 1 / len(slice_)
    columns = [column for column in ["date", "ticker", "sector", "rank", "weight"] if column in slice_.columns]
    return slice_[columns]


def equal_weight_sector_neutral_top_n(ranked: pd.DataFrame, date, n: int = 50) -> pd.DataFrame:
    slice_ = ranked.loc[ranked["date"] == pd.Timestamp(date)].sort_values("rank").copy()
    if slice_.empty or "sector" not in slice_.columns:
        return equal_weight_top_n(ranked, date, n=n)

    sector_groups = {
        sector: frame.sort_values("rank").to_dict(orient="records")
        for sector, frame in slice_.groupby("sector", dropna=False)
    }
    selected = []
    while len(selected) < n and any(sector_groups.values()):
        for sector in sorted(sector_groups, key=lambda value: str(value)):
            records = sector_groups[sector]
            if records:
                selected.append(records.pop(0))
            if len(selected) == n:
                break

    if not selected:
        return pd.DataFrame(columns=["date", "ticker", "weight"])

    portfolio = pd.DataFrame(selected)
    portfolio["weight"] = 1 / len(portfolio)
    columns = [
        column for column in ["date", "ticker", "sector", "rank", "weight"] if column in portfolio.columns
    ]
    return portfolio[columns]


def calculate_turnover(current: pd.Series, previous: pd.Series | None) -> float:
    if previous is None:
        return float(current.abs().sum())
    aligned = pd.concat([current, previous], axis=1).fillna(0)
    aligned.columns = ["current", "previous"]
    return float((aligned["current"] - aligned["previous"]).abs().sum() / 2)
