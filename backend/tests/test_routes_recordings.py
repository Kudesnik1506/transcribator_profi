import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.api.main import app
from app.db import Base, get_db
from app.models import Chunk, Recording, Segment, Summary
from app.queue import get_queue


class FakeQueue:
    def __init__(self):
        self.enqueued = []

    async def enqueue_job(self, function, *args):
        self.enqueued.append((function, args))


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
def fake_queue():
    return FakeQueue()


@pytest.fixture
def client(db_session, fake_queue):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_queue] = lambda: fake_queue
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_recording_persists_and_enqueues_job(client, db_session, fake_queue, auth_headers, active_user):
    response = client.post(
        "/recordings",
        json={"s3_key": "media/abc-file.mp4", "original_filename": "file.mp4"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"

    saved = db_session.get(Recording, body["id"])
    assert saved is not None
    assert saved.s3_key_media == "media/abc-file.mp4"
    assert saved.original_filename == "file.mp4"
    assert saved.user_id == active_user.id

    assert fake_queue.enqueued == [("process_recording_job", (body["id"],))]


def test_create_recording_rejects_missing_fields(client, auth_headers):
    response = client.post("/recordings", json={}, headers=auth_headers)

    assert response.status_code == 422


def test_create_recording_requires_auth(client):
    response = client.post("/recordings", json={"s3_key": "k", "original_filename": "f.mp4"})

    assert response.status_code == 401


def test_create_recording_defaults_mode_from_settings(client, db_session, auth_headers, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "default_processing_mode", "fast")

    response = client.post(
        "/recordings", json={"s3_key": "k", "original_filename": "f.mp4"}, headers=auth_headers
    )

    saved = db_session.get(Recording, response.json()["id"])
    assert saved.mode == "fast"


def test_create_recording_accepts_explicit_mode(client, db_session, auth_headers):
    response = client.post(
        "/recordings",
        json={"s3_key": "k", "original_filename": "f.mp4", "mode": "fast"},
        headers=auth_headers,
    )

    saved = db_session.get(Recording, response.json()["id"])
    assert saved.mode == "fast"


def test_create_recording_rejects_invalid_mode(client, auth_headers):
    response = client.post(
        "/recordings",
        json={"s3_key": "k", "original_filename": "f.mp4", "mode": "turbo"},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_get_recording_includes_mode(client, db_session, auth_headers, active_user):
    recording = Recording(
        user_id=active_user.id, original_filename="f.mp4", s3_key_media="k", status="done", mode="fast"
    )
    db_session.add(recording)
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}", headers=auth_headers)

    assert response.json()["mode"] == "fast"


def test_list_recordings_includes_mode(client, db_session, auth_headers, active_user):
    recording = Recording(
        user_id=active_user.id, original_filename="f.mp4", s3_key_media="k", status="done", mode="fast"
    )
    db_session.add(recording)
    db_session.commit()

    response = client.get("/recordings", headers=auth_headers)

    assert response.json()[0]["mode"] == "fast"


def test_get_recording_returns_segments_and_summary(client, db_session, auth_headers, active_user):
    recording = Recording(user_id=active_user.id, original_filename="f.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()
    segment = Segment(recording_id=recording.id, start_ms=0, end_ms=1000, text="привет")
    db_session.add(segment)
    db_session.add(Summary(recording_id=recording.id, items=["п1"], model="gpt-4o-mini"))
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["segments"] == [{"id": segment.id, "start_ms": 0, "end_ms": 1000, "text": "привет"}]
    assert body["summary"] == {"items": ["п1"]}


def test_get_recording_returns_media_url_and_content_type(client, db_session, auth_headers, active_user):
    recording = Recording(
        user_id=active_user.id,
        original_filename="f.mp4",
        s3_key_media="media/f.mp4",
        content_type="video/mp4",
        status="done",
    )
    db_session.add(recording)
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}", headers=auth_headers)

    body = response.json()
    assert body["content_type"] == "video/mp4"
    assert body["media_url"].startswith("http")
    assert "f.mp4" in body["media_url"]
    assert body["media_deleted_at"] is None


def test_get_recording_hides_media_url_when_media_deleted(client, db_session, auth_headers, active_user):
    from datetime import datetime, timezone

    recording = Recording(
        user_id=active_user.id,
        original_filename="f.mp4",
        s3_key_media="media/f.mp4",
        status="done",
        media_deleted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(recording)
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}", headers=auth_headers)

    body = response.json()
    assert body["media_url"] is None
    assert body["media_deleted_at"] is not None


def test_create_recording_persists_content_type(client, db_session, auth_headers):
    response = client.post(
        "/recordings",
        json={"s3_key": "media/abc-file.mp4", "original_filename": "file.mp4", "content_type": "video/mp4"},
        headers=auth_headers,
    )

    saved = db_session.get(Recording, response.json()["id"])
    assert saved.content_type == "video/mp4"


def test_get_recording_404_when_missing(client, auth_headers):
    response = client.get("/recordings/does-not-exist", headers=auth_headers)

    assert response.status_code == 404


def test_get_recording_404_when_not_owner(client, db_session, auth_headers):
    other_owner_recording = Recording(user_id="someone-else", original_filename="f.mp4", s3_key_media="k")
    db_session.add(other_owner_recording)
    db_session.commit()

    response = client.get(f"/recordings/{other_owner_recording.id}", headers=auth_headers)

    assert response.status_code == 404


def test_get_recording_admin_can_open_any_users_recording(client, db_session, admin_auth_headers):
    other_owner_recording = Recording(user_id="someone-else", original_filename="f.mp4", s3_key_media="k")
    db_session.add(other_owner_recording)
    db_session.commit()

    response = client.get(f"/recordings/{other_owner_recording.id}", headers=admin_auth_headers)

    assert response.status_code == 200


def test_get_recording_summary_null_when_not_ready(client, db_session, auth_headers, active_user):
    recording = Recording(
        user_id=active_user.id, original_filename="f.mp4", s3_key_media="k", status="transcribing"
    )
    db_session.add(recording)
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}", headers=auth_headers)

    assert response.json()["summary"] is None


def test_get_recording_returns_error_message_when_failed(client, db_session, auth_headers, active_user):
    recording = Recording(
        user_id=active_user.id,
        original_filename="f.mp4",
        s3_key_media="k",
        status="failed",
        error_message="s3 is down",
    )
    db_session.add(recording)
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}", headers=auth_headers)

    assert response.json()["error_message"] == "s3 is down"


def test_get_recording_returns_progress_percent(client, db_session, auth_headers, active_user):
    recording = Recording(
        user_id=active_user.id,
        original_filename="f.mp4",
        s3_key_media="k",
        status="transcribing",
        progress_percent=42,
    )
    db_session.add(recording)
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}", headers=auth_headers)

    assert response.json()["progress_percent"] == 42


def test_retry_recording_enqueues_retry_job(client, db_session, fake_queue, auth_headers, active_user):
    recording = Recording(user_id=active_user.id, original_filename="f.mp4", s3_key_media="k", status="partial")
    db_session.add(recording)
    db_session.commit()
    db_session.add(Chunk(recording_id=recording.id, idx=0, start_sec=0, end_sec=900, status="failed"))
    db_session.commit()

    response = client.post(f"/recordings/{recording.id}/retry", headers=auth_headers)

    assert response.status_code == 202
    assert fake_queue.enqueued == [("retry_failed_chunks_job", (recording.id,))]


def test_retry_recording_404_when_missing(client, auth_headers):
    response = client.post("/recordings/does-not-exist/retry", headers=auth_headers)

    assert response.status_code == 404


def test_retry_recording_rejects_when_not_partial(client, db_session, fake_queue, auth_headers, active_user):
    recording = Recording(user_id=active_user.id, original_filename="f.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()

    response = client.post(f"/recordings/{recording.id}/retry", headers=auth_headers)

    assert response.status_code == 409
    assert fake_queue.enqueued == []


def test_list_recordings_returns_newest_first(client, db_session, auth_headers, active_user):
    older = Recording(
        user_id=active_user.id, original_filename="a.mp4", s3_key_media="k1", status="done", progress_percent=100
    )
    db_session.add(older)
    db_session.commit()
    newer = Recording(
        user_id=active_user.id,
        original_filename="b.mp4",
        s3_key_media="k2",
        status="transcribing",
        progress_percent=40,
    )
    db_session.add(newer)
    db_session.commit()

    response = client.get("/recordings", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert [r["id"] for r in body] == [newer.id, older.id]
    assert body[0]["original_filename"] == "b.mp4"
    assert body[0]["status"] == "transcribing"
    assert body[0]["progress_percent"] == 40
    assert "created_at" in body[0]


def test_list_recordings_empty(client, auth_headers):
    response = client.get("/recordings", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_list_recordings_excludes_other_users_recordings(client, db_session, auth_headers, active_user):
    db_session.add(Recording(user_id="someone-else", original_filename="a.mp4", s3_key_media="k1"))
    db_session.commit()

    response = client.get("/recordings", headers=auth_headers)

    assert response.json() == []


def test_create_recording_rejects_fourth_upload_over_quota(client, db_session, auth_headers, active_user):
    from app.config import settings

    for i in range(settings.daily_upload_quota):
        db_session.add(
            Recording(user_id=active_user.id, original_filename=f"f{i}.mp4", s3_key_media=f"k{i}", status="queued")
        )
    db_session.commit()

    response = client.post(
        "/recordings", json={"s3_key": "k4", "original_filename": "f4.mp4"}, headers=auth_headers
    )

    assert response.status_code == 429
    assert "лимит" in response.json()["detail"].lower()


def test_create_recording_failed_uploads_dont_count_against_quota(client, db_session, auth_headers, active_user):
    from app.config import settings

    for i in range(settings.daily_upload_quota):
        db_session.add(
            Recording(user_id=active_user.id, original_filename=f"f{i}.mp4", s3_key_media=f"k{i}", status="failed")
        )
    db_session.commit()

    response = client.post(
        "/recordings", json={"s3_key": "k4", "original_filename": "f4.mp4"}, headers=auth_headers
    )

    assert response.status_code == 201


def test_create_recording_admin_not_limited_by_quota(client, db_session, admin_auth_headers, admin_user):
    from app.config import settings

    for i in range(settings.daily_upload_quota):
        db_session.add(
            Recording(user_id=admin_user.id, original_filename=f"f{i}.mp4", s3_key_media=f"k{i}", status="queued")
        )
    db_session.commit()

    response = client.post(
        "/recordings", json={"s3_key": "k4", "original_filename": "f4.mp4"}, headers=admin_auth_headers
    )

    assert response.status_code == 201
