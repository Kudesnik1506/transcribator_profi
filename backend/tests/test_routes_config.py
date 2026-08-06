from fastapi.testclient import TestClient

from app.api.main import app
from app.config import settings

client = TestClient(app)


def test_get_config_returns_default_processing_mode(monkeypatch):
    monkeypatch.setattr(settings, "default_processing_mode", "fast")

    response = client.get("/config")

    assert response.status_code == 200
    assert response.json()["default_processing_mode"] == "fast"
