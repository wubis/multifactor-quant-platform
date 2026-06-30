import pandas as pd

from multifactor_platform.features.momentum import add_momentum_features
from multifactor_platform.features.normalization import latest_fundamentals_asof, normalize_cross_section
from multifactor_platform.features.volatility import add_volatility_features


FACTOR_COLUMNS = [
    "momentum_1m",
    "momentum_3m",
    "momentum_6m",
    "momentum_12m_ex_1m",
    "volatility_20d",
    "volatility_60d",
    "beta_252d",
    "pe_ratio",
    "pb_ratio",
    "fcf_yield",
    "roe",
    "gross_margin",
    "debt_to_equity",
    "earnings_stability",
    "market_cap",
    "dollar_volume",
]


def build_feature_frame(prices: pd.DataFrame, fundamentals: pd.DataFrame) -> pd.DataFrame:
    features = add_momentum_features(prices)
    features = add_volatility_features(features)
    features["dollar_volume"] = features["adj_close"] * features["volume"]
    features = latest_fundamentals_asof(features, fundamentals)
    features = features.loc[features["ticker"] != "SPY"].copy()
    existing = [column for column in FACTOR_COLUMNS if column in features.columns]
    return normalize_cross_section(features, existing)
