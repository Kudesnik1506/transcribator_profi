import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.routes_recordings as routes_recordings
import app.models  # noqa: F401 - registers tables on Base.metadata
from app.api.main import app
from app.config import settings
from app.db import Base, get_db
from app.models import Message, Recording, Segment
from app.queue import get_queue


class FakeQueue:
    async def enqueue_job(self, function, *args):
        pass


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def db_session(engine):
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(db_session, engine, monkeypatch):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_queue] = lambda: FakeQueue()
    monkeypatch.setattr(routes_recordings, "SessionLocal", sessionmaker(bind=engine))
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_ask_question_streams_answer_and_persists_messages(client, db_session, monkeypatch):
    recording = Recording(original_filename="m.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()
    db_session.add(Segment(recording_id=recording.id, start_ms=0, end_ms=1000, text="говорили про бюджет"))
    db_session.commit()

    monkeypatch.setattr(
        routes_recordings, "stream_answer", lambda messages: iter(["Про", " бюджет", " сказали..."])
    )

    response = client.post(f"/recordings/{recording.id}/messages", json={"content": "что сказали про бюджет?"})

    assert response.status_code == 200
    assert response.text == "Про бюджет сказали..."

    messages = (
        db_session.query(Message).filter_by(recording_id=recording.id).order_by(Message.created_at).all()
    )
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "что сказали про бюджет?"
    assert messages[1].role == "assistant"
    assert messages[1].content == "Про бюджет сказали..."


def test_ask_question_streams_friendly_message_on_upstream_failure(client, db_session, monkeypatch):
    recording = Recording(original_filename="m.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()
    db_session.add(Segment(recording_id=recording.id, start_ms=0, end_ms=1000, text="текст"))
    db_session.commit()

    def boom(messages):
        raise RuntimeError("upstream boom")

    monkeypatch.setattr(routes_recordings, "stream_answer", boom)

    response = client.post(f"/recordings/{recording.id}/messages", json={"content": "вопрос"})

    assert response.status_code == 200
    assert "недоступен" in response.text.lower() or "не удалось" in response.text.lower()

    messages = (
        db_session.query(Message).filter_by(recording_id=recording.id).order_by(Message.created_at).all()
    )
    assert len(messages) == 2
    assert messages[1].role == "assistant"


def test_ask_question_404_when_recording_missing(client):
    response = client.post("/recordings/does-not-exist/messages", json={"content": "вопрос"})

    assert response.status_code == 404


def test_ask_question_409_when_no_transcript_yet(client, db_session):
    recording = Recording(original_filename="m.mp4", s3_key_media="k", status="transcribing")
    db_session.add(recording)
    db_session.commit()

    response = client.post(f"/recordings/{recording.id}/messages", json={"content": "вопрос"})

    assert response.status_code == 409


def test_ask_question_409_when_still_transcribing_even_with_partial_segments(client, db_session):
    recording = Recording(original_filename="m.mp4", s3_key_media="k", status="transcribing")
    db_session.add(recording)
    db_session.commit()
    db_session.add(Segment(recording_id=recording.id, start_ms=0, end_ms=1000, text="только первый кусок"))
    db_session.commit()

    response = client.post(f"/recordings/{recording.id}/messages", json={"content": "вопрос"})

    assert response.status_code == 409


def test_ask_question_allowed_when_partial_status(client, db_session, monkeypatch):
    recording = Recording(original_filename="m.mp4", s3_key_media="k", status="partial")
    db_session.add(recording)
    db_session.commit()
    db_session.add(Segment(recording_id=recording.id, start_ms=0, end_ms=1000, text="то что успели"))
    db_session.commit()

    monkeypatch.setattr(routes_recordings, "stream_answer", lambda messages: iter(["ответ"]))

    response = client.post(f"/recordings/{recording.id}/messages", json={"content": "вопрос"})

    assert response.status_code == 200


def test_ask_question_413_when_transcript_too_long(client, db_session, monkeypatch):
    recording = Recording(original_filename="m.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()
    db_session.add(Segment(recording_id=recording.id, start_ms=0, end_ms=1000, text="x" * 1_000_000))
    db_session.commit()

    monkeypatch.setattr(settings, "max_dialog_context_tokens", 100)

    response = client.post(f"/recordings/{recording.id}/messages", json={"content": "вопрос"})

    assert response.status_code == 413


def test_list_messages_returns_history(client, db_session):
    recording = Recording(original_filename="m.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()
    db_session.add(Message(recording_id=recording.id, role="user", content="вопрос 1"))
    db_session.add(Message(recording_id=recording.id, role="assistant", content="ответ 1"))
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}/messages")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["role"] == "user"
    assert body[0]["content"] == "вопрос 1"
    assert body[1]["role"] == "assistant"


def test_list_messages_404_when_recording_missing(client):
    response = client.get("/recordings/does-not-exist/messages")

    assert response.status_code == 404
