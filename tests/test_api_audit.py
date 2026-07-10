from fastapi.testclient import TestClient

from app.main import app


def test_get_report_not_found_returns_structured_404() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/audit/reports/does-not-exist")
    assert response.status_code == 404
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert body["code"] == "REPORT_NOT_FOUND"


def test_correction_requires_session_id() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/audit/verdicts/TXN-0001/correct", json={"notes": "test"})
    assert response.status_code == 422  # missing required session_id field


def test_correction_on_nonexistent_episode_returns_structured_404() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/audit/verdicts/TXN-0001/correct", json={"session_id": "does-not-exist", "notes": "test"}
    )
    assert response.status_code == 404
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert body["code"] == "EPISODE_NOT_FOUND"
