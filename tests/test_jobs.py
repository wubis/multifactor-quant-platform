from multifactor_platform.jobs.compute_features import run as run_compute_features
from multifactor_platform.jobs.evaluate_models import run as run_evaluate_models
from multifactor_platform.jobs.ingest_prices import run as run_ingest_prices
from multifactor_platform.jobs.run_backtest import run as run_backtest


def test_ingest_prices_job_reports_sample_quality():
    result = run_ingest_prices("sample")

    assert result["source"] == "sample"
    assert result["row_count"] > 0
    assert result["ticker_count"] > 0


def test_compute_features_job_returns_counts():
    result = run_compute_features("sample")

    assert result["feature_rows"] > 0
    assert result["ranking_rows"] > 0
    assert result["latest_ranked_stocks"] > 0


def test_run_backtest_job_returns_metrics():
    result = run_backtest("sample", top_n=5)

    assert result["periods"] > 0
    assert "sharpe" in result["metrics"]


def test_evaluate_models_job_returns_walk_forward_results():
    result = run_evaluate_models("sample")

    assert result["source"] == "sample"
    assert result["models"]
    assert any(model["name"] == "Linear Regression" for model in result["models"])
