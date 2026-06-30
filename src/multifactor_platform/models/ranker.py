import pandas as pd

from multifactor_platform.models.weighted_score import score_weighted_model


def rank_stocks(features: pd.DataFrame) -> pd.DataFrame:
    scored = score_weighted_model(features)
    ranked = scored.copy()
    ranked["rank"] = ranked.groupby("date")["composite_score"].rank(
        method="first", ascending=False
    )
    return ranked.sort_values(["date", "rank"]).reset_index(drop=True)
