from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

import app.api.routes_uploads as routes_uploads
from app.api.main import app
from app.s3 import UploadedPart

client = TestClient(app)


def test_create_multipart_returns_upload_id_and_part_plan(monkeypatch):
    monkeypatch.setattr(routes_uploads, "create_multipart_upload", lambda key, content_type: "upload-123")

    response = client.post(
        "/uploads/multipart",
        json={"filename": "big.mp4", "content_type": "video/mp4", "size_bytes": 40 * 1024 * 1024},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["upload_id"] == "upload-123"
    assert body["s3_key"].endswith("big.mp4")
    assert body["part_size"] == 16 * 1024 * 1024
    assert body["part_count"] == 3


def test_create_multipart_rejects_oversized_file():
    response = client.post(
        "/uploads/multipart",
        json={"filename": "huge.mp4", "content_type": "video/mp4", "size_bytes": 3 * 1024**3},
    )

    assert response.status_code == 413


def test_create_multipart_rejects_zero_size():
    response = client.post(
        "/uploads/multipart",
        json={"filename": "empty.mp4", "content_type": "video/mp4", "size_bytes": 0},
    )

    assert response.status_code == 422


def test_get_part_upload_url(monkeypatch):
    monkeypatch.setattr(
        routes_uploads,
        "presign_upload_part_url",
        lambda key, upload_id, part_number: f"https://s3.example/{key}?part={part_number}&uid={upload_id}",
    )

    response = client.post("/uploads/multipart/upload-123/parts/2", json={"s3_key": "media/abc-big.mp4"})

    assert response.status_code == 200
    assert "part=2" in response.json()["upload_url"]


def test_get_uploaded_parts(monkeypatch):
    monkeypatch.setattr(
        routes_uploads,
        "list_uploaded_parts",
        lambda key, upload_id: [UploadedPart(part_number=1, etag='"abc"', size=1000)],
    )

    response = client.get("/uploads/multipart/upload-123/parts", params={"s3_key": "media/abc-big.mp4"})

    assert response.status_code == 200
    assert response.json() == [{"part_number": 1, "etag": '"abc"', "size": 1000}]


def test_complete_multipart(monkeypatch):
    calls = {}

    def fake_complete(key, upload_id, parts):
        calls["key"] = key
        calls["upload_id"] = upload_id
        calls["parts"] = parts

    monkeypatch.setattr(routes_uploads, "complete_multipart_upload", fake_complete)

    response = client.post(
        "/uploads/multipart/upload-123/complete",
        json={"s3_key": "media/abc-big.mp4", "parts": [{"part_number": 1, "etag": '"abc"'}]},
    )

    assert response.status_code == 204
    assert calls["upload_id"] == "upload-123"
    assert calls["key"] == "media/abc-big.mp4"
    assert calls["parts"][0].part_number == 1
    assert calls["parts"][0].etag == '"abc"'


def test_create_multipart_returns_clean_error_on_s3_failure(monkeypatch):
    def boom(key, content_type):
        raise ClientError({"Error": {"Code": "InvalidArgument", "Message": "bad request"}}, "CreateMultipartUpload")

    monkeypatch.setattr(routes_uploads, "create_multipart_upload", boom)

    response = client.post(
        "/uploads/multipart",
        json={"filename": "big.mp4", "content_type": "video/mp4", "size_bytes": 1000},
    )

    assert response.status_code == 502
    assert "detail" in response.json()


def test_abort_multipart(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        routes_uploads,
        "abort_multipart_upload",
        lambda key, upload_id: calls.update(key=key, upload_id=upload_id),
    )

    response = client.post("/uploads/multipart/upload-123/abort", json={"s3_key": "media/abc-big.mp4"})

    assert response.status_code == 204
    assert calls == {"key": "media/abc-big.mp4", "upload_id": "upload-123"}
