import pandas as pd


def add_value_scores(features: pd.DataFrame) -> pd.DataFrame:
    output = features.copy()
    output["value_score_raw"] = (
        -output["pe_ratio"].rank(pct=True)
        - output["pb_ratio"].rank(pct=True)
        + output["fcf_yield"].rank(pct=True)
    )
    return output
