from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DataQualityReport:
    source: str
    is_research_grade: bool
    row_count: int
    ticker_count: int
    start_date: str | None
    end_date: str | None
    warnings: list[str]


def validate_price_history(prices: pd.DataFrame, source: str) -> DataQualityReport:
    warnings = []
    if prices.empty:
        warnings.append("Price history is empty.")
        return DataQualityReport(source, False, 0, 0, None, None, warnings)

    duplicate_count = int(prices.duplicated(["ticker", "date"]).sum())
    if duplicate_count:
        warnings.append(f"Found {duplicate_count} duplicate ticker/date price rows.")

    non_positive = (prices[["open", "high", "low", "close", "adj_close"]] <= 0).any(axis=1)
    if bool(non_positive.any()):
        warnings.append(f"Found {int(non_positive.sum())} rows with non-positive prices.")

    missing_adj_close = int(prices["adj_close"].isna().sum())
    if missing_adj_close:
        warnings.append(f"Found {missing_adj_close} rows missing adjusted close.")

    ticker_lengths = prices.groupby("ticker")["date"].nunique()
    sparse_tickers = ticker_lengths[ticker_lengths < 252]
    if not sparse_tickers.empty:
        warnings.append(
            f"{len(sparse_tickers)} tickers have less than one trading year of observations."
        )

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
        ticker_count=int(prices["ticker"].nunique()),
        start_date=start.date().isoformat() if pd.notna(start) else None,
        end_date=end.date().isoformat() if pd.notna(end) else None,
        warnings=warnings,
    )


def report_to_dict(report: DataQualityReport) -> dict:
    return {
        "source": report.source,
        "is_research_grade": report.is_research_grade,
        "row_count": report.row_count,
        "ticker_count": report.ticker_count,
        "start_date": report.start_date,
        "end_date": report.end_date,
        "warnings": report.warnings,
    }
