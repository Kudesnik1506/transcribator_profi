import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.db import Base
from app.models import Recording, Segment, Summary
from app.worker import tasks
from app.worker.speechkit_client import Segment as SpeechKitSegment


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_process_recording_runs_pipeline_to_done(db_session, tmp_path, monkeypatch):
    recording = Recording(original_filename="meeting.mp4", s3_key_media="media/meeting.mp4", status="queued")
    db_session.add(recording)
    db_session.commit()

    monkeypatch.setattr(tasks, "download_media", lambda s3_key, dest: dest.write_bytes(b"fake-media"))
    monkeypatch.setattr(
        tasks, "extract_audio", lambda media_path, audio_path: audio_path.write_bytes(b"fake-audio")
    )
    monkeypatch.setattr(
        tasks,
        "transcribe",
        lambda audio_bytes: [SpeechKitSegment(start_ms=0, end_ms=1000, text="привет мир")],
    )
    monkeypatch.setattr(tasks, "summarize", lambda transcript: ["Пункт сводки"])

    tasks.process_recording(db_session, recording.id, work_dir=tmp_path)

    db_session.refresh(recording)
    assert recording.status == "done"

    segments = db_session.query(Segment).filter_by(recording_id=recording.id).all()
    assert len(segments) == 1
    assert segments[0].text == "привет мир"
    assert segments[0].start_ms == 0
    assert segments[0].end_ms == 1000

    summary = db_session.query(Summary).filter_by(recording_id=recording.id).one()
    assert summary.items == ["Пункт сводки"]


def test_process_recording_marks_failed_on_exception(db_session, tmp_path, monkeypatch):
    recording = Recording(original_filename="meeting.mp4", s3_key_media="media/meeting.mp4", status="queued")
    db_session.add(recording)
    db_session.commit()

    def boom(*args, **kwargs):
        raise RuntimeError("s3 is down")

    monkeypatch.setattr(tasks, "download_media", boom)

    with pytest.raises(RuntimeError):
        tasks.process_recording(db_session, recording.id, work_dir=tmp_path)

    db_session.refresh(recording)
    assert recording.status == "failed"
    assert "s3 is down" in recording.error_message
