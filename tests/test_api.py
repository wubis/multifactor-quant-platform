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
    assert "/rankings/latest" in response.json()["endpoints"]
