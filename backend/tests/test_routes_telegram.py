from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.api import routes_telegram
from app.api.main import app
from app.db import Base, get_db
from app.models import TelegramLinkCode, User


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


def test_create_link_code_requires_auth(client):
    response = client.post("/telegram/link-code")

    assert response.status_code == 401


def test_create_link_code_returns_code_and_expiry(client, db_session, auth_headers, active_user):
    response = client.post("/telegram/link-code", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["code"]
    saved = db_session.query(TelegramLinkCode).filter_by(user_id=active_user.id).first()
    assert saved is not None
    assert saved.code == body["code"]


def test_create_link_code_replaces_previous_code(client, db_session, auth_headers, active_user):
    client.post("/telegram/link-code", headers=auth_headers)
    client.post("/telegram/link-code", headers=auth_headers)

    codes = db_session.query(TelegramLinkCode).filter_by(user_id=active_user.id).all()
    assert len(codes) == 1


def test_webhook_links_chat_id_on_valid_code(client, db_session, active_user, monkeypatch):
    monkeypatch.setattr(routes_telegram, "send_telegram_text", lambda chat_id, text: None)
    link = TelegramLinkCode(
        user_id=active_user.id, code="abc123", expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    db_session.add(link)
    db_session.commit()

    response = client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 555}, "text": "/start abc123"}},
    )

    assert response.status_code == 200
    db_session.refresh(active_user)
    assert active_user.telegram_chat_id == "555"
    assert db_session.query(TelegramLinkCode).filter_by(code="abc123").first() is None


def test_webhook_rejects_expired_code(client, db_session, active_user, monkeypatch):
    monkeypatch.setattr(routes_telegram, "send_telegram_text", lambda chat_id, text: None)
    link = TelegramLinkCode(
        user_id=active_user.id, code="old123", expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    db_session.add(link)
    db_session.commit()

    response = client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 555}, "text": "/start old123"}},
    )

    assert response.status_code == 200
    db_session.refresh(active_user)
    assert active_user.telegram_chat_id is None


def test_webhook_rejects_unknown_code(client, db_session, monkeypatch):
    monkeypatch.setattr(routes_telegram, "send_telegram_text", lambda chat_id, text: None)

    response = client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 555}, "text": "/start does-not-exist"}},
    )

    assert response.status_code == 200


def test_webhook_ignores_non_start_messages(client, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(routes_telegram, "send_telegram_text", lambda chat_id, text: calls.append((chat_id, text)))

    response = client.post("/telegram/webhook", json={"message": {"chat": {"id": 555}, "text": "привет"}})

    assert response.status_code == 200
    assert calls == []


def test_webhook_tolerates_missing_message(client, db_session):
    response = client.post("/telegram/webhook", json={"update_id": 1})

    assert response.status_code == 200


def test_webhook_rejects_wrong_secret_token_when_configured(client, db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "telegram_webhook_secret", "correct-secret")

    response = client.post(
        "/telegram/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )

    assert response.status_code == 401


def test_webhook_accepts_correct_secret_token_when_configured(client, db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "telegram_webhook_secret", "correct-secret")

    response = client.post(
        "/telegram/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "correct-secret"},
    )

    assert response.status_code == 200


def test_webhook_allows_any_caller_when_secret_not_configured(client, db_session):
    response = client.post("/telegram/webhook", json={"update_id": 1})

    assert response.status_code == 200


def test_unlink_clears_chat_id_and_pending_codes(client, db_session, auth_headers, active_user):
    active_user.telegram_chat_id = "555"
    db_session.add(TelegramLinkCode(user_id=active_user.id, code="abc123", expires_at=datetime.now(timezone.utc)))
    db_session.commit()

    response = client.post("/telegram/unlink", headers=auth_headers)

    assert response.status_code == 204
    db_session.refresh(active_user)
    assert active_user.telegram_chat_id is None
    assert db_session.query(TelegramLinkCode).filter_by(user_id=active_user.id).first() is None


def test_unlink_requires_auth(client):
    response = client.post("/telegram/unlink")

    assert response.status_code == 401


def test_webhook_survives_telegram_reply_failure(client, db_session, active_user, monkeypatch):
    from app.worker.notify import TelegramDeliveryError

    def failing_send(chat_id, text):
        raise TelegramDeliveryError("bot down")

    monkeypatch.setattr(routes_telegram, "send_telegram_text", failing_send)
    link = TelegramLinkCode(
        user_id=active_user.id, code="abc123", expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    db_session.add(link)
    db_session.commit()

    response = client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 555}, "text": "/start abc123"}},
    )

    assert response.status_code == 200
    db_session.refresh(active_user)
    assert active_user.telegram_chat_id == "555"
