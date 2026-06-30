from functools import lru_cache

from multifactor_platform.features.pipeline import build_feature_frame
from multifactor_platform.ingestion.fundamentals import prepare_fundamentals
from multifactor_platform.ingestion.prices import prepare_prices
from multifactor_platform.ingestion.sample_data import make_sample_fundamentals, make_sample_prices
from multifactor_platform.models.ranker import rank_stocks


@lru_cache
def load_sample_platform_data():
    prices = prepare_prices(make_sample_prices())
    fundamentals = prepare_fundamentals(make_sample_fundamentals())
    features = build_feature_frame(prices, fundamentals).dropna(
        subset=[
            "momentum_12m_ex_1m_z",
            "volatility_60d_z",
            "pe_ratio_z",
            "roe_z",
            "market_cap_z",
        ]
    )
    rankings = rank_stocks(features)
    return prices, features, rankings
