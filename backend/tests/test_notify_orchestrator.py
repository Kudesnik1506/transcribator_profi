import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.db import Base
from app.models import ErrorLog, Recording, User
from app.worker import notify
from app.worker.notify import EmailDeliveryError, TelegramDeliveryError, notify_recording_finished


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
def user(db_session):
    u = User(email="user@example.com", password_hash="x", status="active")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def recording(db_session, user):
    r = Recording(user_id=user.id, original_filename="f.mp4", s3_key_media="k", status="done")
    db_session.add(r)
    db_session.commit()
    return r


def test_notify_sends_email_and_marks_notified(db_session, recording, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send_email", lambda *args: sent.append(args))

    notify_recording_finished(db_session, recording)

    assert sent == [("user@example.com", "f.mp4", "done", recording.id)]
    assert recording.notified_at is not None


def test_notify_is_a_noop_if_already_notified_for_the_same_status(db_session, recording, monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "send_email", lambda *args: calls.append(args))
    from datetime import datetime, timezone

    recording.notified_at = datetime.now(timezone.utc)
    recording.notified_status = recording.status
    db_session.commit()

    notify_recording_finished(db_session, recording)

    assert calls == []


def test_notify_sends_again_when_a_retry_changed_the_outcome(db_session, recording, monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "send_email", lambda *args: calls.append(args))
    from datetime import datetime, timezone

    recording.notified_at = datetime.now(timezone.utc)
    recording.notified_status = "partial"
    recording.status = "done"
    db_session.commit()

    notify_recording_finished(db_session, recording)

    assert calls == [("user@example.com", "f.mp4", "done", recording.id)]
    assert recording.notified_status == "done"


def test_notify_skips_telegram_when_not_linked(db_session, recording, monkeypatch):
    monkeypatch.setattr(notify, "send_email", lambda *args: None)
    telegram_calls = []
    monkeypatch.setattr(notify, "send_telegram_message", lambda *args: telegram_calls.append(args))

    notify_recording_finished(db_session, recording)

    assert telegram_calls == []


def test_notify_sends_telegram_when_linked(db_session, recording, user, monkeypatch):
    user.telegram_chat_id = "chat-1"
    db_session.commit()

    monkeypatch.setattr(notify, "send_email", lambda *args: None)
    telegram_calls = []
    monkeypatch.setattr(notify, "send_telegram_message", lambda *args: telegram_calls.append(args))

    notify_recording_finished(db_session, recording)

    assert telegram_calls == [("chat-1", "f.mp4", "done", recording.id)]


def test_notify_logs_error_and_still_marks_notified_when_email_fails(db_session, recording, monkeypatch):
    def failing_send_email(*args):
        raise EmailDeliveryError("smtp down")

    monkeypatch.setattr(notify, "send_email", failing_send_email)

    notify_recording_finished(db_session, recording)

    assert recording.notified_at is not None
    logs = db_session.query(ErrorLog).filter_by(recording_id=recording.id).all()
    assert any("smtp" in log.message.lower() for log in logs)


def test_notify_logs_error_when_telegram_fails_independently_of_email(db_session, recording, user, monkeypatch):
    user.telegram_chat_id = "chat-1"
    db_session.commit()

    monkeypatch.setattr(notify, "send_email", lambda *args: None)

    def failing_telegram(*args):
        raise TelegramDeliveryError("bot down")

    monkeypatch.setattr(notify, "send_telegram_message", failing_telegram)

    notify_recording_finished(db_session, recording)

    assert recording.notified_at is not None
    logs = db_session.query(ErrorLog).filter_by(recording_id=recording.id).all()
    assert any("bot down" in log.message.lower() for log in logs)


def test_notify_noop_when_recording_has_no_owner(db_session, monkeypatch):
    orphan = Recording(user_id=None, original_filename="f.mp4", s3_key_media="k", status="done")
    db_session.add(orphan)
    db_session.commit()

    calls = []
    monkeypatch.setattr(notify, "send_email", lambda *args: calls.append(args))

    notify_recording_finished(db_session, orphan)

    assert calls == []
    assert orphan.notified_at is not None
