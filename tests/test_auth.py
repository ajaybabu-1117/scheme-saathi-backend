from fastapi.testclient import TestClient

from app.main import app


def test_anonymous_auth():
    client = TestClient(app)
    response = client.post("/api/v1/auth/anonymous")
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["is_anonymous"] is True
