from functools import lru_cache
from typing import Literal

import pandas as pd

from multifactor_platform.config import get_settings
from multifactor_platform.features.pipeline import build_feature_frame
from multifactor_platform.ingestion.fundamentals import prepare_fundamentals
from multifactor_platform.ingestion.prices import prepare_prices
from multifactor_platform.ingestion.sample_data import make_sample_fundamentals, make_sample_prices
from multifactor_platform.ingestion.universe import load_large_cap_universe
from multifactor_platform.ingestion.yfinance_client import (
    fetch_yfinance_fundamentals,
    fetch_yfinance_prices,
)
from multifactor_platform.models.ranker import rank_stocks

DataSource = Literal["sample", "yfinance", "point_in_time"]

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
        medians = output.groupby("date")[column].transform("median")
        output[column] = output[column].fillna(medians)
    return output


def _finalize_pipeline(prices: pd.DataFrame, fundamentals: pd.DataFrame):
    price_attrs = dict(prices.attrs)
    fundamental_attrs = dict(fundamentals.attrs)
    prepared_prices = prepare_prices(prices)
    prepared_prices.attrs.update(price_attrs)
    prepared_prices.attrs["fundamental_failed_tickers"] = fundamental_attrs.get("failed_tickers", [])
    prepared_prices.attrs["fundamental_cache_hit"] = fundamental_attrs.get("cache_hit")
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
def load_yfinance_platform_data(
    period: str | None = None,
    universe_limit: int | None = None,
    batch_size: int | None = None,
):
    settings = get_settings()
    selected_period = period or settings.yfinance_period
    selected_universe_limit = universe_limit or settings.yfinance_universe_limit
    selected_batch_size = batch_size or settings.yfinance_batch_size
    universe = load_large_cap_universe(limit=selected_universe_limit)
    prices = fetch_yfinance_prices(
        universe=universe,
        period=selected_period,
        batch_size=selected_batch_size,
    )
    fundamentals = fetch_yfinance_fundamentals(universe=universe)
    result = _finalize_pipeline(prices, fundamentals)
    for frame in result:
        frame.attrs["historical_research_blocked"] = (
            "Historical yfinance multifactor research is unavailable: fundamentals are "
            "current snapshots, not point-in-time history. Supply historical fundamentals "
            "with availability dates; use sample data for offline pipeline testing."
        )
    return result


def load_platform_data(source: DataSource = "sample"):
    if source == "sample":
        return load_sample_platform_data()
    if source == "yfinance":
        return load_yfinance_platform_data()
    if source == "point_in_time":
        from multifactor_platform.ingestion.point_in_time import build_point_in_time_data
        from multifactor_platform.research import ResearchDataError
        path = get_settings().point_in_time_dataset
        if not path:
            raise ResearchDataError("Import a point-in-time packet and set MFP_POINT_IN_TIME_DATASET to its archive path")
        try:
            return build_point_in_time_data(path)
        except (OSError, KeyError, ValueError) as exc:
            raise ResearchDataError(f"Point-in-time dataset unavailable or invalid: {exc}") from exc
    raise ValueError(f"Unknown data source: {source}")
