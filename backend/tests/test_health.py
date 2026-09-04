from fastapi.testclient import TestClient
from app.main import app


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


def test_registered_routes():
    """
    Verify that all required v1 recovery, auth, and health routes are properly
    registered and exposed on the FastAPI application OpenAPI schema.
    """
    openapi_schema = app.openapi()
    openapi_paths = list(openapi_schema.get("paths", {}).keys())

    expected_routes = [
        "/api/v1/health",
        "/api/v1/auth/me",
        "/api/v1/recovery/batches",
        "/api/v1/recovery/seed-demo-batch",
        "/api/v1/recovery/cases",
        "/api/v1/recovery/cases/{case_id}",
        "/api/v1/recovery/cases/{case_id}/run",
        "/api/v1/recovery/metrics",
    ]

    for expected_path in expected_routes:
        assert expected_path in openapi_paths, (
            f"Expected route '{expected_path}' not found in exposed OpenAPI paths: {openapi_paths}"
        )
