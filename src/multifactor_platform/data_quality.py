from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DataQualityReport:
    source: str
    is_research_grade: bool
    row_count: int
    ticker_count: int
    expected_ticker_count: int | None
    coverage_ratio: float | None
    start_date: str | None
    end_date: str | None
    failed_tickers: list[str]
    stale_tickers: list[str]
    sparse_tickers: list[str]
    outlier_return_count: int
    zero_volume_count: int
    cache_hit: bool | None
    warnings: list[str]


def validate_price_history(prices: pd.DataFrame, source: str) -> DataQualityReport:
    warnings = []
    attrs = prices.attrs
    if prices.empty:
        warnings.append("Price history is empty.")
        return DataQualityReport(
            source,
            False,
            0,
            0,
            attrs.get("expected_ticker_count"),
            None,
            None,
            None,
            attrs.get("failed_tickers", []),
            [],
            [],
            0,
            0,
            attrs.get("cache_hit"),
            warnings,
        )

    duplicate_count = int(prices.duplicated(["ticker", "date"]).sum())
    if duplicate_count:
        warnings.append(f"Found {duplicate_count} duplicate ticker/date price rows.")

    non_positive = (prices[["open", "high", "low", "close", "adj_close"]] <= 0).any(axis=1)
    if bool(non_positive.any()):
        warnings.append(f"Found {int(non_positive.sum())} rows with non-positive prices.")

    missing_adj_close = int(prices["adj_close"].isna().sum())
    if missing_adj_close:
        warnings.append(f"Found {missing_adj_close} rows missing adjusted close.")

    zero_volume_count = int((prices["volume"].fillna(0) <= 0).sum())
    if zero_volume_count:
        warnings.append(f"Found {zero_volume_count} rows with zero or missing volume.")

    ticker_lengths = prices.groupby("ticker")["date"].nunique()
    sparse_ticker_index = ticker_lengths[ticker_lengths < 252].index.tolist()
    if sparse_ticker_index:
        warnings.append(
            f"{len(sparse_ticker_index)} tickers have less than one trading year of observations."
        )

    latest_date = pd.to_datetime(prices["date"]).max()
    ticker_latest_dates = pd.to_datetime(prices.groupby("ticker")["date"].max())
    stale_cutoff = latest_date - pd.Timedelta(days=10)
    stale_tickers = sorted(ticker_latest_dates[ticker_latest_dates < stale_cutoff].index.tolist())
    if stale_tickers:
        warnings.append(f"{len(stale_tickers)} tickers have stale latest price dates.")

    returns = prices.sort_values(["ticker", "date"]).groupby("ticker")["adj_close"].pct_change()
    outlier_return_count = int((returns.abs() > 0.35).sum())
    if outlier_return_count:
        warnings.append(f"Found {outlier_return_count} daily adjusted returns larger than 35%.")

    failed_tickers = sorted(set(attrs.get("failed_tickers", [])))
    if failed_tickers:
        warnings.append(f"{len(failed_tickers)} expected tickers failed yfinance price ingestion.")

    fundamental_failed_tickers = sorted(set(attrs.get("fundamental_failed_tickers", [])))
    if fundamental_failed_tickers:
        warnings.append(
            f"{len(fundamental_failed_tickers)} tickers failed yfinance fundamental ingestion."
        )

    expected_ticker_count = attrs.get("expected_ticker_count")
    ticker_count = int(prices["ticker"].nunique())
    coverage_ratio = ticker_count / expected_ticker_count if expected_ticker_count else None
    if coverage_ratio is not None and coverage_ratio < 0.95:
        warnings.append(f"Ticker coverage is {coverage_ratio:.1%}, below the 95% target.")

    if source == "yfinance":
        warnings.append(
            "yfinance is a demo data source, not a point-in-time institutional dataset."
        )
        warnings.append(
            "Current yfinance fundamentals are applied as a snapshot, so historical backtests are not research-grade."
        )

    start = pd.to_datetime(prices["date"]).min()
    end = pd.to_datetime(prices["date"]).max()
    return DataQualityReport(
        source=source,
        is_research_grade=not warnings,
        row_count=len(prices),
        ticker_count=ticker_count,
        expected_ticker_count=expected_ticker_count,
        coverage_ratio=coverage_ratio,
        start_date=start.date().isoformat() if pd.notna(start) else None,
        end_date=end.date().isoformat() if pd.notna(end) else None,
        failed_tickers=failed_tickers,
        stale_tickers=stale_tickers,
        sparse_tickers=sorted(sparse_ticker_index),
        outlier_return_count=outlier_return_count,
        zero_volume_count=zero_volume_count,
        cache_hit=attrs.get("cache_hit"),
        warnings=warnings,
    )


def report_to_dict(report: DataQualityReport) -> dict:
    return {
        "source": report.source,
        "is_research_grade": report.is_research_grade,
        "row_count": report.row_count,
        "ticker_count": report.ticker_count,
        "expected_ticker_count": report.expected_ticker_count,
        "coverage_ratio": report.coverage_ratio,
        "start_date": report.start_date,
        "end_date": report.end_date,
        "failed_tickers": report.failed_tickers,
        "stale_tickers": report.stale_tickers,
        "sparse_tickers": report.sparse_tickers,
        "outlier_return_count": report.outlier_return_count,
        "zero_volume_count": report.zero_volume_count,
        "cache_hit": report.cache_hit,
        "warnings": report.warnings,
    }
