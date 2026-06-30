from multifactor_platform.features.pipeline import build_feature_frame
from multifactor_platform.ingestion.sample_data import make_sample_fundamentals, make_sample_prices
from multifactor_platform.models.ranker import rank_stocks


def test_ranker_assigns_one_top_rank_per_date():
    features = build_feature_frame(make_sample_prices(), make_sample_fundamentals()).dropna()
    rankings = rank_stocks(features)
    latest = rankings.loc[rankings["date"] == rankings["date"].max()]

    assert latest["rank"].min() == 1
    assert latest["rank"].is_unique
    assert latest["composite_score"].notna().all()
