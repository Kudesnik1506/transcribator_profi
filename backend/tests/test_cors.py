from fastapi.testclient import TestClient

from app.api.main import app
from app.config import settings

client = TestClient(app)


def test_frontend_origin_receives_cors_headers():
    response = client.get("/config", headers={"Origin": settings.frontend_base_url})

    assert response.headers["access-control-allow-origin"] == settings.frontend_base_url


def test_preflight_request_is_allowed_for_frontend_origin():
    response = client.options(
        "/auth/register",
        headers={
            "Origin": settings.frontend_base_url,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == settings.frontend_base_url
