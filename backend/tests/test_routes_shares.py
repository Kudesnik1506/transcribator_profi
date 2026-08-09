import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.api.main import app
from app.auth import create_access_token, hash_password
from app.db import Base, get_db
from app.models import Recording, RecordingShare, User
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


@pytest.fixture
def recipient(db_session):
    user = User(email="recipient@example.com", password_hash=hash_password("password123"), role="user", status="active")
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def recipient_auth_headers(recipient):
    return {"Authorization": f"Bearer {create_access_token(recipient.id)}"}


@pytest.fixture
def recording(db_session, active_user):
    recording = Recording(user_id=active_user.id, original_filename="f.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()
    return recording


def test_create_share_grants_access_to_recipient(client, db_session, auth_headers, recording, recipient):
    response = client.post(
        f"/recordings/{recording.id}/shares", json={"email": recipient.email}, headers=auth_headers
    )

    assert response.status_code == 201
    assert response.json()["email"] == recipient.email
    share = db_session.query(RecordingShare).filter_by(recording_id=recording.id).first()
    assert share is not None
    assert share.shared_with_user_id == recipient.id


def test_create_share_is_idempotent(client, db_session, auth_headers, recording, recipient):
    client.post(f"/recordings/{recording.id}/shares", json={"email": recipient.email}, headers=auth_headers)
    client.post(f"/recordings/{recording.id}/shares", json={"email": recipient.email}, headers=auth_headers)

    shares = db_session.query(RecordingShare).filter_by(recording_id=recording.id).all()
    assert len(shares) == 1


def test_create_share_404_for_unknown_email(client, auth_headers, recording):
    response = client.post(
        f"/recordings/{recording.id}/shares", json={"email": "nobody@example.com"}, headers=auth_headers
    )

    assert response.status_code == 404


def test_create_share_rejects_sharing_with_self(client, auth_headers, recording, active_user):
    response = client.post(
        f"/recordings/{recording.id}/shares", json={"email": active_user.email}, headers=auth_headers
    )

    assert response.status_code == 400


def test_create_share_404_when_not_owner(client, recipient_auth_headers, recording):
    response = client.post(
        f"/recordings/{recording.id}/shares", json={"email": "someone@example.com"}, headers=recipient_auth_headers
    )

    assert response.status_code == 404


def test_recipient_can_read_shared_recording(client, db_session, auth_headers, recipient_auth_headers, recording, recipient):
    client.post(f"/recordings/{recording.id}/shares", json={"email": recipient.email}, headers=auth_headers)

    response = client.get(f"/recordings/{recording.id}", headers=recipient_auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["is_owner"] is False
    assert body["owner_email"] == "user@example.com"


def test_recipient_cannot_read_unshared_recording(client, recipient_auth_headers, recording):
    response = client.get(f"/recordings/{recording.id}", headers=recipient_auth_headers)

    assert response.status_code == 404


def test_recipient_cannot_retry(client, db_session, auth_headers, recipient_auth_headers, recording, recipient):
    recording.status = "partial"
    db_session.commit()
    client.post(f"/recordings/{recording.id}/shares", json={"email": recipient.email}, headers=auth_headers)

    response = client.post(f"/recordings/{recording.id}/retry", headers=recipient_auth_headers)

    assert response.status_code == 404


def test_recipient_cannot_ask_question(client, auth_headers, recipient_auth_headers, recording, recipient):
    client.post(f"/recordings/{recording.id}/shares", json={"email": recipient.email}, headers=auth_headers)

    response = client.post(
        f"/recordings/{recording.id}/messages", json={"content": "?"}, headers=recipient_auth_headers
    )

    assert response.status_code == 404


def test_list_shares_returns_recipients(client, auth_headers, recording, recipient):
    client.post(f"/recordings/{recording.id}/shares", json={"email": recipient.email}, headers=auth_headers)

    response = client.get(f"/recordings/{recording.id}/shares", headers=auth_headers)

    assert response.status_code == 200
    assert [s["email"] for s in response.json()] == [recipient.email]


def test_revoke_share_removes_access(client, db_session, auth_headers, recipient_auth_headers, recording, recipient):
    share = client.post(
        f"/recordings/{recording.id}/shares", json={"email": recipient.email}, headers=auth_headers
    ).json()

    response = client.delete(f"/recordings/{recording.id}/shares/{share['id']}", headers=auth_headers)

    assert response.status_code == 204
    assert client.get(f"/recordings/{recording.id}", headers=recipient_auth_headers).status_code == 404


def test_shared_with_me_lists_recording_with_owner_email(
    client, auth_headers, recipient_auth_headers, recording, recipient
):
    client.post(f"/recordings/{recording.id}/shares", json={"email": recipient.email}, headers=auth_headers)

    response = client.get("/recordings/shared-with-me", headers=recipient_auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == recording.id
    assert body[0]["owner_email"] == "user@example.com"


def test_shared_with_me_empty_for_unshared_user(client, recipient_auth_headers):
    response = client.get("/recordings/shared-with-me", headers=recipient_auth_headers)

    assert response.status_code == 200
    assert response.json() == []
