from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
import app.recording_deletion as recording_deletion
from app.api.main import app
from app.db import Base, get_db
from app.models import Recording, RecordingShare, TelegramLinkCode, User


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


def test_register_creates_pending_user(client, db_session):
    response = client.post("/auth/register", json={"email": "a@example.com", "password": "verysecret123"})

    assert response.status_code == 201
    assert response.json()["status"] == "pending"

    user = db_session.query(User).filter_by(email="a@example.com").first()
    assert user is not None
    assert user.password_hash != "verysecret123"
    assert user.role == "user"


def test_register_rejects_duplicate_email(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "verysecret123"})

    response = client.post("/auth/register", json={"email": "a@example.com", "password": "anotherpass1"})

    assert response.status_code == 409


def test_register_rejects_short_password(client):
    response = client.post("/auth/register", json={"email": "a@example.com", "password": "short"})

    assert response.status_code == 422


def test_register_rejects_password_over_bcrypt_byte_limit(client):
    # bcrypt silently truncates at 72 bytes — two different passwords sharing
    # a 72-byte prefix would otherwise hash identically and both authenticate.
    response = client.post("/auth/register", json={"email": "a@example.com", "password": "a" * 73})

    assert response.status_code == 422


def test_login_returns_token_for_correct_credentials(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "verysecret123"})

    response = client.post("/auth/login", json={"email": "a@example.com", "password": "verysecret123"})

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_rejects_wrong_password(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "verysecret123"})

    response = client.post("/auth/login", json={"email": "a@example.com", "password": "wrongpassword"})

    assert response.status_code == 401


def test_login_rejects_unknown_email(client):
    response = client.post("/auth/login", json={"email": "nobody@example.com", "password": "verysecret123"})

    assert response.status_code == 401


def test_login_rejects_blocked_user(client, db_session):
    client.post("/auth/register", json={"email": "a@example.com", "password": "verysecret123"})
    user = db_session.query(User).filter_by(email="a@example.com").first()
    user.status = "blocked"
    db_session.commit()

    response = client.post("/auth/login", json={"email": "a@example.com", "password": "verysecret123"})

    assert response.status_code == 403


def test_login_allows_pending_user_to_get_token(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "verysecret123"})

    response = client.post("/auth/login", json={"email": "a@example.com", "password": "verysecret123"})

    assert response.status_code == 200


def test_me_returns_current_user_info(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "verysecret123"})
    token = client.post(
        "/auth/login", json={"email": "a@example.com", "password": "verysecret123"}
    ).json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "a@example.com"
    assert body["status"] == "pending"
    assert body["role"] == "user"
    assert body["telegram_linked"] is False


def test_me_rejects_missing_token(client):
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_me_rejects_invalid_token(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})

    assert response.status_code == 401


def test_delete_me_removes_user_and_owned_recordings(
    client, db_session, auth_headers, active_user, monkeypatch
):
    monkeypatch.setattr(recording_deletion, "delete_media", lambda key: None)
    recording = Recording(user_id=active_user.id, original_filename="f.mp4", s3_key_media="k")
    db_session.add(recording)
    db_session.add(
        TelegramLinkCode(
            user_id=active_user.id, code="abc123", expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
    )
    db_session.commit()

    response = client.delete("/auth/me", headers=auth_headers)

    assert response.status_code == 204
    assert db_session.get(User, active_user.id) is None
    assert db_session.get(Recording, recording.id) is None
    assert db_session.query(TelegramLinkCode).filter_by(user_id=active_user.id).first() is None


def test_delete_me_removes_shares_granted_to_the_user(client, db_session, auth_headers, active_user):
    owner = User(email="owner@example.com", password_hash="x", role="user", status="active")
    db_session.add(owner)
    db_session.commit()
    recording = Recording(user_id=owner.id, original_filename="f.mp4", s3_key_media="k")
    db_session.add(recording)
    db_session.commit()
    db_session.add(RecordingShare(recording_id=recording.id, shared_with_user_id=active_user.id))
    db_session.commit()

    response = client.delete("/auth/me", headers=auth_headers)

    assert response.status_code == 204
    assert db_session.query(RecordingShare).filter_by(shared_with_user_id=active_user.id).first() is None
    # Owner and their recording are untouched.
    assert db_session.get(User, owner.id) is not None
    assert db_session.get(Recording, recording.id) is not None


def test_delete_me_requires_auth(client):
    response = client.delete("/auth/me")

    assert response.status_code == 401


def test_token_invalid_after_account_deleted(client, db_session, auth_headers, active_user, monkeypatch):
    monkeypatch.setattr(recording_deletion, "delete_media", lambda key: None)
    client.delete("/auth/me", headers=auth_headers)

    response = client.get("/auth/me", headers=auth_headers)

    assert response.status_code == 401
