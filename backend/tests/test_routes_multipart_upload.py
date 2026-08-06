import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.routes_uploads as routes_uploads
from app.api.main import app
from app.config import settings
from app.db import Base, get_db
from app.models import Recording  # also registers all tables on Base.metadata
from app.s3 import UploadedPart


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_multipart_returns_upload_id_and_part_plan(client, monkeypatch, auth_headers):
    monkeypatch.setattr(routes_uploads, "create_multipart_upload", lambda key, content_type: "upload-123")

    response = client.post(
        "/uploads/multipart",
        json={"filename": "big.mp4", "content_type": "video/mp4", "size_bytes": 40 * 1024 * 1024},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["upload_id"] == "upload-123"
    assert body["s3_key"].endswith("big.mp4")
    assert body["part_size"] == 16 * 1024 * 1024
    assert body["part_count"] == 3


def test_create_multipart_requires_auth(client):
    response = client.post(
        "/uploads/multipart",
        json={"filename": "big.mp4", "content_type": "video/mp4", "size_bytes": 1000},
    )

    assert response.status_code == 401


def test_create_multipart_rejects_oversized_file(client, auth_headers):
    response = client.post(
        "/uploads/multipart",
        json={"filename": "huge.mp4", "content_type": "video/mp4", "size_bytes": 3 * 1024**3},
        headers=auth_headers,
    )

    assert response.status_code == 413


def test_create_multipart_rejects_zero_size(client, auth_headers):
    response = client.post(
        "/uploads/multipart",
        json={"filename": "empty.mp4", "content_type": "video/mp4", "size_bytes": 0},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_get_part_upload_url(client, monkeypatch, auth_headers):
    monkeypatch.setattr(
        routes_uploads,
        "presign_upload_part_url",
        lambda key, upload_id, part_number: f"https://s3.example/{key}?part={part_number}&uid={upload_id}",
    )

    response = client.post(
        "/uploads/multipart/upload-123/parts/2", json={"s3_key": "media/abc-big.mp4"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert "part=2" in response.json()["upload_url"]


def test_get_uploaded_parts(client, monkeypatch, auth_headers):
    monkeypatch.setattr(
        routes_uploads,
        "list_uploaded_parts",
        lambda key, upload_id: [UploadedPart(part_number=1, etag='"abc"', size=1000)],
    )

    response = client.get(
        "/uploads/multipart/upload-123/parts", params={"s3_key": "media/abc-big.mp4"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json() == [{"part_number": 1, "etag": '"abc"', "size": 1000}]


def test_complete_multipart(client, monkeypatch, auth_headers):
    calls = {}

    def fake_complete(key, upload_id, parts):
        calls["key"] = key
        calls["upload_id"] = upload_id
        calls["parts"] = parts

    monkeypatch.setattr(routes_uploads, "complete_multipart_upload", fake_complete)

    response = client.post(
        "/uploads/multipart/upload-123/complete",
        json={"s3_key": "media/abc-big.mp4", "parts": [{"part_number": 1, "etag": '"abc"'}]},
        headers=auth_headers,
    )

    assert response.status_code == 204
    assert calls["upload_id"] == "upload-123"
    assert calls["key"] == "media/abc-big.mp4"
    assert calls["parts"][0].part_number == 1
    assert calls["parts"][0].etag == '"abc"'


def test_create_multipart_returns_clean_error_on_s3_failure(client, monkeypatch, auth_headers):
    def boom(key, content_type):
        raise ClientError({"Error": {"Code": "InvalidArgument", "Message": "bad request"}}, "CreateMultipartUpload")

    monkeypatch.setattr(routes_uploads, "create_multipart_upload", boom)

    response = client.post(
        "/uploads/multipart",
        json={"filename": "big.mp4", "content_type": "video/mp4", "size_bytes": 1000},
        headers=auth_headers,
    )

    assert response.status_code == 502
    assert "detail" in response.json()


def test_create_multipart_rejects_when_quota_exceeded(client, db_session, auth_headers, active_user):
    for i in range(settings.daily_upload_quota):
        db_session.add(
            Recording(user_id=active_user.id, original_filename=f"f{i}.mp4", s3_key_media=f"k{i}", status="queued")
        )
    db_session.commit()

    response = client.post(
        "/uploads/multipart",
        json={"filename": "big.mp4", "content_type": "video/mp4", "size_bytes": 1000},
        headers=auth_headers,
    )

    assert response.status_code == 429
    assert "лимит" in response.json()["detail"].lower()


def test_create_multipart_admin_not_limited_by_quota(client, db_session, monkeypatch, admin_auth_headers, admin_user):
    monkeypatch.setattr(routes_uploads, "create_multipart_upload", lambda key, content_type: "upload-123")

    for i in range(settings.daily_upload_quota):
        db_session.add(
            Recording(user_id=admin_user.id, original_filename=f"f{i}.mp4", s3_key_media=f"k{i}", status="queued")
        )
    db_session.commit()

    response = client.post(
        "/uploads/multipart",
        json={"filename": "big.mp4", "content_type": "video/mp4", "size_bytes": 1000},
        headers=admin_auth_headers,
    )

    assert response.status_code == 200


def test_abort_multipart(client, monkeypatch, auth_headers):
    calls = {}
    monkeypatch.setattr(
        routes_uploads,
        "abort_multipart_upload",
        lambda key, upload_id: calls.update(key=key, upload_id=upload_id),
    )

    response = client.post(
        "/uploads/multipart/upload-123/abort", json={"s3_key": "media/abc-big.mp4"}, headers=auth_headers
    )

    assert response.status_code == 204
    assert calls == {"key": "media/abc-big.mp4", "upload_id": "upload-123"}
