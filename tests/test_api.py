from fastapi.testclient import TestClient

from multifactor_platform.api.main import app


def test_health_endpoint():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint_lists_entry_points():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"
    assert "/rankings/latest?source=yfinance" in response.json()["endpoints"]


def test_sample_rankings_endpoint_runs_offline():
    client = TestClient(app)

    response = client.get("/rankings/latest?source=sample&limit=3")

    assert response.status_code == 200
    assert response.json()["source"] == "sample"
    assert len(response.json()["rankings"]) == 3


def test_data_quality_endpoint_runs_offline():
    client = TestClient(app)

    response = client.get("/data-quality/report?source=sample")

    assert response.status_code == 200
    assert response.json()["row_count"] > 0
    assert "warnings" in response.json()


def test_optimized_portfolio_endpoint_runs_offline():
    client = TestClient(app)

    response = client.get("/portfolio/optimized?source=sample&candidate_limit=20")

    assert response.status_code == 200
    assert response.json()["source"] == "sample"
    assert response.json()["positions"]
    assert response.json()["cash_weight"] >= 0


def test_backtest_detail_exposes_benchmark_cost_and_risk_series():
    client = TestClient(app)

    response = client.get("/backtests/sample-top-10?source=sample")

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["benchmark_cagr"] is not None
    assert body["settings"]["rebalance_delay_days"] == 1
    assert body["benchmark_returns"]
    assert body["excess_returns"]
    assert body["turnover"]
    assert body["costs"]
    assert body["sector_exposure"]
    assert body["rebalance_log"]


def test_models_endpoint_runs_walk_forward_models_offline():
    client = TestClient(app)

    response = client.get("/models?source=sample")

    assert response.status_code == 200
    body = response.json()
    names = {row["name"] for row in body["models"]}
    assert {"Weighted Score", "Linear Regression", "Elastic Net", "Random Forest", "Gradient Boosting"}.issubset(names)
    linear = next(row for row in body["models"] if row["name"] == "Linear Regression")
    assert linear["fold_count"] > 0
    assert linear["rank_ic"] is not None
