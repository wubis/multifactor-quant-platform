import pandas as pd


FACTOR_EXPOSURE_COLUMNS = {
    "beta": "beta_252d",
    "size": "market_cap_z",
    "value": "value_score",
    "momentum": "momentum_score",
    "volatility": "volatility_60d_z",
    "liquidity": "dollar_volume_z",
    "quality": "quality_score",
}


def compute_factor_exposures(holdings: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    if holdings.empty or features.empty:
        return pd.DataFrame(columns=["date", "factor", "exposure"])

    available_columns = {
        factor: column for factor, column in FACTOR_EXPOSURE_COLUMNS.items() if column in features.columns
    }
    if not available_columns:
        return pd.DataFrame(columns=["date", "factor", "exposure"])

    feature_columns = ["date", "ticker", *available_columns.values()]
    feature_frame = features[feature_columns].copy()
    feature_frame["date"] = pd.to_datetime(feature_frame["date"])

    holding_frame = holdings[[column for column in ["date", "ticker", "weight", "signal_date"] if column in holdings]].copy()
    holding_frame["date"] = pd.to_datetime(holding_frame["date"])

    if "signal_date" in holding_frame:
        feature_frame = feature_frame.rename(columns={"date": "signal_date"})
        merged = holding_frame.merge(feature_frame, on=["signal_date", "ticker"], how="left")
    else:
        merged = holding_frame.merge(feature_frame, on=["date", "ticker"], how="left")
    rows = []
    for date, frame in merged.groupby("date"):
        weights = frame["weight"].fillna(0)
        for factor, column in available_columns.items():
            if frame.loc[weights > 0, column].isna().any():
                continue  # Missing exposures are unavailable, not zero risk.
            values = frame[column].fillna(0)
            rows.append(
                {
                    "date": pd.Timestamp(date),
                    "factor": factor,
                    "exposure": float((weights * values).sum()),
                }
            )

    return pd.DataFrame(rows).sort_values(["date", "factor"]).reset_index(drop=True)


def latest_factor_exposure_summary(factor_exposures: pd.DataFrame) -> dict[str, float]:
    if factor_exposures.empty:
        return {}

    latest_date = pd.to_datetime(factor_exposures["date"]).max()
    latest = factor_exposures.loc[pd.to_datetime(factor_exposures["date"]) == latest_date]
    return {
        row["factor"]: float(row["exposure"])
        for _, row in latest.sort_values("factor").iterrows()
    }
