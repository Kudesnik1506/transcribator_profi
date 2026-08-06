import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.api.main import app
from app.db import Base, get_db
from app.models import Chunk, ErrorLog, Message, Recording, Segment, Summary, User


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


# --- access control ---


def test_admin_routes_reject_missing_auth(client):
    assert client.get("/admin/users").status_code == 401
    assert client.get("/admin/recordings").status_code == 401
    assert client.get("/admin/error-logs").status_code == 401


def test_admin_routes_reject_regular_user(client, auth_headers):
    assert client.get("/admin/users", headers=auth_headers).status_code == 403
    assert client.get("/admin/recordings", headers=auth_headers).status_code == 403
    assert client.get("/admin/error-logs", headers=auth_headers).status_code == 403


def test_admin_routes_allow_admin(client, admin_auth_headers):
    assert client.get("/admin/users", headers=admin_auth_headers).status_code == 200
    assert client.get("/admin/recordings", headers=admin_auth_headers).status_code == 200
    assert client.get("/admin/error-logs", headers=admin_auth_headers).status_code == 200


# --- users ---


def test_list_users_returns_all_users(client, db_session, admin_auth_headers, admin_user, active_user):
    response = client.get("/admin/users", headers=admin_auth_headers)

    emails = {u["email"] for u in response.json()}
    assert emails == {admin_user.email, active_user.email}


def test_approve_user_sets_status_active(client, db_session, admin_auth_headers):
    pending = User(email="pending@example.com", password_hash="x", role="user", status="pending")
    db_session.add(pending)
    db_session.commit()

    response = client.post(f"/admin/users/{pending.id}/approve", headers=admin_auth_headers)

    assert response.status_code == 200
    db_session.refresh(pending)
    assert pending.status == "active"


def test_block_user_sets_status_blocked(client, db_session, admin_auth_headers, active_user):
    response = client.post(f"/admin/users/{active_user.id}/block", headers=admin_auth_headers)

    assert response.status_code == 200
    db_session.refresh(active_user)
    assert active_user.status == "blocked"


def test_admin_cannot_block_themselves(client, db_session, admin_auth_headers, admin_user):
    response = client.post(f"/admin/users/{admin_user.id}/block", headers=admin_auth_headers)

    assert response.status_code == 400
    db_session.refresh(admin_user)
    assert admin_user.status == "active"


def test_approve_user_404_when_missing(client, admin_auth_headers):
    response = client.post("/admin/users/does-not-exist/approve", headers=admin_auth_headers)

    assert response.status_code == 404


# --- recordings ---


def test_list_all_recordings_includes_other_users_recordings(client, db_session, admin_auth_headers, active_user):
    db_session.add(Recording(user_id=active_user.id, original_filename="a.mp4", s3_key_media="k1", status="done"))
    db_session.commit()

    response = client.get("/admin/recordings", headers=admin_auth_headers)

    assert len(response.json()) == 1
    assert response.json()[0]["original_filename"] == "a.mp4"
    assert response.json()[0]["user_email"] == active_user.email


def test_list_all_recordings_filters_by_user(client, db_session, admin_auth_headers, active_user, admin_user):
    db_session.add(Recording(user_id=active_user.id, original_filename="a.mp4", s3_key_media="k1"))
    db_session.add(Recording(user_id=admin_user.id, original_filename="b.mp4", s3_key_media="k2"))
    db_session.commit()

    response = client.get(f"/admin/recordings?user_id={active_user.id}", headers=admin_auth_headers)

    assert [r["original_filename"] for r in response.json()] == ["a.mp4"]


def test_list_all_recordings_filters_by_status(client, db_session, admin_auth_headers, active_user):
    db_session.add(Recording(user_id=active_user.id, original_filename="a.mp4", s3_key_media="k1", status="done"))
    db_session.add(Recording(user_id=active_user.id, original_filename="b.mp4", s3_key_media="k2", status="failed"))
    db_session.commit()

    response = client.get("/admin/recordings?status=failed", headers=admin_auth_headers)

    assert [r["original_filename"] for r in response.json()] == ["b.mp4"]


def test_delete_recording_removes_media_from_s3(client, db_session, admin_auth_headers, active_user, monkeypatch):
    import app.recording_deletion as recording_deletion

    deleted_keys = []
    monkeypatch.setattr(recording_deletion, "delete_media", lambda key: deleted_keys.append(key))

    recording = Recording(user_id=active_user.id, original_filename="a.mp4", s3_key_media="media/a.mp4")
    db_session.add(recording)
    db_session.commit()

    response = client.delete(f"/admin/recordings/{recording.id}", headers=admin_auth_headers)

    assert response.status_code == 204
    assert deleted_keys == ["media/a.mp4"]
    assert db_session.get(Recording, recording.id) is None


def test_delete_recording_removes_related_rows(client, db_session, admin_auth_headers, active_user, monkeypatch):
    import app.recording_deletion as recording_deletion

    monkeypatch.setattr(recording_deletion, "delete_media", lambda key: None)

    recording = Recording(user_id=active_user.id, original_filename="a.mp4", s3_key_media="media/a.mp4")
    db_session.add(recording)
    db_session.commit()
    chunk = Chunk(recording_id=recording.id, idx=0, start_sec=0, end_sec=900, status="done")
    db_session.add(chunk)
    db_session.add(Segment(recording_id=recording.id, chunk_id=chunk.id, start_ms=0, end_ms=1000, text="привет"))
    db_session.add(Summary(recording_id=recording.id, items=["п1"], model="gpt-4o-mini"))
    db_session.add(Message(recording_id=recording.id, role="user", content="вопрос"))
    db_session.add(ErrorLog(recording_id=recording.id, level="error", message="упс", context={}))
    db_session.commit()

    response = client.delete(f"/admin/recordings/{recording.id}", headers=admin_auth_headers)

    assert response.status_code == 204
    assert db_session.query(Chunk).filter_by(recording_id=recording.id).count() == 0
    assert db_session.query(Segment).filter_by(recording_id=recording.id).count() == 0
    assert db_session.query(Summary).filter_by(recording_id=recording.id).count() == 0
    assert db_session.query(Message).filter_by(recording_id=recording.id).count() == 0
    assert db_session.query(ErrorLog).filter_by(recording_id=recording.id).count() == 0


def test_delete_recording_404_when_missing(client, admin_auth_headers):
    response = client.delete("/admin/recordings/does-not-exist", headers=admin_auth_headers)

    assert response.status_code == 404


def test_delete_recording_rejected_for_regular_user(client, db_session, auth_headers, active_user):
    recording = Recording(user_id=active_user.id, original_filename="a.mp4", s3_key_media="k1")
    db_session.add(recording)
    db_session.commit()

    response = client.delete(f"/admin/recordings/{recording.id}", headers=auth_headers)

    assert response.status_code == 403
    assert db_session.get(Recording, recording.id) is not None


# --- error logs ---


def test_list_error_logs_returns_all(client, db_session, admin_auth_headers):
    db_session.add(ErrorLog(recording_id=None, level="error", message="упс", context={}))
    db_session.commit()

    response = client.get("/admin/error-logs", headers=admin_auth_headers)

    assert len(response.json()) == 1
    assert response.json()[0]["message"] == "упс"


def test_list_error_logs_filters_by_level(client, db_session, admin_auth_headers):
    db_session.add(ErrorLog(recording_id=None, level="error", message="ошибка", context={}))
    db_session.add(ErrorLog(recording_id=None, level="warning", message="предупреждение", context={}))
    db_session.commit()

    response = client.get("/admin/error-logs?level=warning", headers=admin_auth_headers)

    assert [log["message"] for log in response.json()] == ["предупреждение"]


def test_list_error_logs_filters_by_recording(client, db_session, admin_auth_headers, active_user):
    recording = Recording(user_id=active_user.id, original_filename="a.mp4", s3_key_media="k1")
    db_session.add(recording)
    db_session.commit()
    db_session.add(ErrorLog(recording_id=recording.id, level="error", message="этой записи", context={}))
    db_session.add(ErrorLog(recording_id=None, level="error", message="другой", context={}))
    db_session.commit()

    response = client.get(f"/admin/error-logs?recording_id={recording.id}", headers=admin_auth_headers)

    assert [log["message"] for log in response.json()] == ["этой записи"]
