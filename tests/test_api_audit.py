from fastapi.testclient import TestClient

from app.main import app


def test_get_report_not_found_returns_structured_404() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/audit/reports/does-not-exist")
    assert response.status_code == 404
    body = response.json()["detail"]
    assert body["status"] == "error"
    assert body["code"] == "REPORT_NOT_FOUND"
