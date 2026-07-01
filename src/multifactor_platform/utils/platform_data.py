from functools import lru_cache
from typing import Literal

import pandas as pd

from multifactor_platform.features.pipeline import build_feature_frame
from multifactor_platform.ingestion.fundamentals import prepare_fundamentals
from multifactor_platform.ingestion.prices import prepare_prices
from multifactor_platform.ingestion.sample_data import make_sample_fundamentals, make_sample_prices
from multifactor_platform.ingestion.yfinance_client import (
    fetch_yfinance_fundamentals,
    fetch_yfinance_prices,
)
from multifactor_platform.models.ranker import rank_stocks

DataSource = Literal["sample", "yfinance"]

MIN_RANKING_COLUMNS = [
    "momentum_12m_ex_1m_z",
    "volatility_60d_z",
    "pe_ratio_z",
    "roe_z",
    "market_cap_z",
]

FUNDAMENTAL_COLUMNS = [
    "pe_ratio",
    "pb_ratio",
    "fcf_yield",
    "roe",
    "gross_margin",
    "debt_to_equity",
    "earnings_stability",
    "market_cap",
]


def _fill_missing_fundamentals(fundamentals: pd.DataFrame) -> pd.DataFrame:
    output = fundamentals.copy()
    for column in FUNDAMENTAL_COLUMNS:
        if column not in output.columns:
            output[column] = pd.NA
        median = output[column].median(skipna=True)
        if pd.isna(median):
            median = 0.0
        output[column] = output[column].fillna(median)
    return output


def _finalize_pipeline(prices: pd.DataFrame, fundamentals: pd.DataFrame):
    prepared_prices = prepare_prices(prices)
    prepared_fundamentals = prepare_fundamentals(_fill_missing_fundamentals(fundamentals))
    features = build_feature_frame(prepared_prices, prepared_fundamentals)
    available_required = [column for column in MIN_RANKING_COLUMNS if column in features.columns]
    features = features.dropna(subset=available_required)
    rankings = rank_stocks(features).dropna(subset=["composite_score"])
    return prepared_prices, features, rankings


@lru_cache
def load_sample_platform_data():
    return _finalize_pipeline(make_sample_prices(), make_sample_fundamentals())


@lru_cache
def load_yfinance_platform_data(period: str = "5y"):
    prices = fetch_yfinance_prices(period=period)
    fundamentals = fetch_yfinance_fundamentals()
    fundamentals["date"] = prices["date"].min()
    return _finalize_pipeline(prices, fundamentals)


def load_platform_data(source: DataSource = "sample"):
    if source == "sample":
        return load_sample_platform_data()
    if source == "yfinance":
        return load_yfinance_platform_data()
    raise ValueError(f"Unknown data source: {source}")
