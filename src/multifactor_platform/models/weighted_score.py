import pandas as pd


DEFAULT_WEIGHTS = {
    "value_score": 0.25,
    "quality_score": 0.25,
    "momentum_score": 0.25,
    "low_vol_score": 0.15,
    "liquidity_score": 0.10,
}


def add_factor_group_scores(features: pd.DataFrame) -> pd.DataFrame:
    output = features.copy()
    output["value_score"] = (
        -output["pe_ratio_z"] - output["pb_ratio_z"] + output["fcf_yield_z"]
    ) / 3
    output["quality_score"] = (
        output["roe_z"]
        + output["gross_margin_z"]
        + output["earnings_stability_z"]
        - output["debt_to_equity_z"]
    ) / 4
    output["momentum_score"] = (
        output["momentum_1m_z"]
        + output["momentum_3m_z"]
        + output["momentum_6m_z"]
        + output["momentum_12m_ex_1m_z"]
    ) / 4
    output["low_vol_score"] = (-output["volatility_20d_z"] - output["volatility_60d_z"]) / 2
    output["liquidity_score"] = (output["market_cap_z"] + output["dollar_volume_z"]) / 2
    return output


def score_weighted_model(
    features: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    output = add_factor_group_scores(features)
    weights = weights or DEFAULT_WEIGHTS
    output["composite_score"] = sum(output[column] * weight for column, weight in weights.items())
    return output
