import pandas as pd


def add_quality_scores(features: pd.DataFrame) -> pd.DataFrame:
    output = features.copy()
    output["quality_score_raw"] = (
        output["roe"].rank(pct=True)
        + output["gross_margin"].rank(pct=True)
        + output["earnings_stability"].rank(pct=True)
        - output["debt_to_equity"].rank(pct=True)
    )
    return output
