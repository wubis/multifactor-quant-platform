import pandas as pd

from multifactor_platform.data_quality import report_to_dict, validate_price_history


def test_price_quality_report_surfaces_ingestion_metadata():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-02"]),
            "ticker": ["AAA", "AAA", "BBB"],
            "open": [10.0, 11.0, 20.0],
            "high": [11.0, 12.0, 21.0],
            "low": [9.0, 10.0, 19.0],
            "close": [10.0, 11.0, 20.0],
            "adj_close": [10.0, 11.0, 20.0],
            "volume": [1000.0, 1000.0, 0.0],
        }
    )
    prices.attrs.update(
        {
            "expected_ticker_count": 3,
            "failed_tickers": ["CCC"],
            "cache_hit": True,
            "period": "10y",
            "universe_limit": 100,
        }
    )

    report = report_to_dict(validate_price_history(prices, "sample"))

    assert report["ticker_count"] == 2
    assert report["expected_ticker_count"] == 3
    assert report["coverage_ratio"] == 2 / 3
    assert report["failed_tickers"] == ["CCC"]
    assert report["zero_volume_count"] == 1
    assert report["cache_hit"] is True
    assert report["source_period"] == "10y"
    assert report["universe_limit"] == 100
