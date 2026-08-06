from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_presign_returns_upload_url_and_s3_key():
    response = client.post("/uploads/presign", json={"filename": "meeting.mp4", "content_type": "video/mp4"})

    assert response.status_code == 200
    body = response.json()
    assert body["upload_url"].startswith("http")
    assert body["s3_key"].endswith("meeting.mp4")


def test_presign_rejects_missing_filename():
    response = client.post("/uploads/presign", json={})

    assert response.status_code == 422
