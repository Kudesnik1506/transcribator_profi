import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.api.main import app
from app.db import Base, get_db
from app.models import Recording, Segment, Summary
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


def test_create_recording_persists_and_enqueues_job(client, db_session, fake_queue):
    response = client.post("/recordings", json={"s3_key": "media/abc-file.mp4", "original_filename": "file.mp4"})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"

    saved = db_session.get(Recording, body["id"])
    assert saved is not None
    assert saved.s3_key_media == "media/abc-file.mp4"
    assert saved.original_filename == "file.mp4"

    assert fake_queue.enqueued == [("process_recording_job", (body["id"],))]


def test_create_recording_rejects_missing_fields(client):
    response = client.post("/recordings", json={})

    assert response.status_code == 422


def test_get_recording_returns_segments_and_summary(client, db_session):
    recording = Recording(original_filename="f.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()
    db_session.add(Segment(recording_id=recording.id, start_ms=0, end_ms=1000, text="привет"))
    db_session.add(Summary(recording_id=recording.id, items=["п1"], model="gpt-4o-mini"))
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["segments"] == [{"start_ms": 0, "end_ms": 1000, "text": "привет"}]
    assert body["summary"] == {"items": ["п1"]}


def test_get_recording_404_when_missing(client):
    response = client.get("/recordings/does-not-exist")

    assert response.status_code == 404


def test_get_recording_summary_null_when_not_ready(client, db_session):
    recording = Recording(original_filename="f.mp4", s3_key_media="k", status="transcribing")
    db_session.add(recording)
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}")

    assert response.json()["summary"] is None


def test_get_recording_returns_error_message_when_failed(client, db_session):
    recording = Recording(
        original_filename="f.mp4", s3_key_media="k", status="failed", error_message="s3 is down"
    )
    db_session.add(recording)
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}")

    assert response.json()["error_message"] == "s3 is down"
