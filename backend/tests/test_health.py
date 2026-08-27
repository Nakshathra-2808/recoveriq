from fastapi.testclient import TestClient


def test_root_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "recoveriq-backend"
    assert data["version"] == "0.1.0"


def test_api_v1_health_check(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "recoveriq-backend"
    assert data["version"] == "0.1.0"


def test_root_endpoint(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "RecoverIQ Backend API" in data["message"]
