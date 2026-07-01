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
