from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.db import Base
from app.models import ErrorLog, Message, Recording
from app.retention import purge_expired_media, purge_expired_recordings, run_retention

NOW = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _make_recording(db_session, created_at, status="done", **kwargs) -> Recording:
    recording = Recording(original_filename="f.mp4", s3_key_media="media/f.mp4", status=status, **kwargs)
    db_session.add(recording)
    db_session.commit()
    recording.created_at = created_at
    db_session.commit()
    return recording


# --- purge_expired_media ---


def test_purge_expired_media_deletes_s3_and_stamps_media_deleted_at(db_session, monkeypatch):
    import app.retention as retention

    deleted_keys = []
    monkeypatch.setattr(retention, "delete_media", lambda key: deleted_keys.append(key))

    old_enough = NOW - timedelta(days=31)
    recording = _make_recording(db_session, old_enough)

    count = purge_expired_media(db_session, NOW, retention_days=30)

    assert count == 1
    assert deleted_keys == ["media/f.mp4"]
    db_session.refresh(recording)
    assert recording.media_deleted_at is not None


def test_purge_expired_media_leaves_transcript_rows_alone(db_session, monkeypatch):
    import app.retention as retention

    monkeypatch.setattr(retention, "delete_media", lambda key: None)

    recording = _make_recording(db_session, NOW - timedelta(days=31))
    from app.models import Segment

    db_session.add(Segment(recording_id=recording.id, start_ms=0, end_ms=1000, text="привет"))
    db_session.commit()

    purge_expired_media(db_session, NOW, retention_days=30)

    assert db_session.get(Recording, recording.id) is not None
    assert db_session.query(Segment).filter_by(recording_id=recording.id).count() == 1


def test_purge_expired_media_skips_recordings_within_retention(db_session, monkeypatch):
    import app.retention as retention

    monkeypatch.setattr(retention, "delete_media", lambda key: (_ for _ in ()).throw(AssertionError("must not be called")))

    _make_recording(db_session, NOW - timedelta(days=10))

    count = purge_expired_media(db_session, NOW, retention_days=30)

    assert count == 0


def test_purge_expired_media_skips_recordings_still_processing(db_session, monkeypatch):
    import app.retention as retention

    monkeypatch.setattr(
        retention, "delete_media", lambda key: (_ for _ in ()).throw(AssertionError("must not be called"))
    )

    _make_recording(db_session, NOW - timedelta(days=31), status="transcribing")

    count = purge_expired_media(db_session, NOW, retention_days=30)

    assert count == 0


def test_purge_expired_media_is_idempotent(db_session, monkeypatch):
    import app.retention as retention

    calls = []
    monkeypatch.setattr(retention, "delete_media", lambda key: calls.append(key))

    _make_recording(db_session, NOW - timedelta(days=31))

    purge_expired_media(db_session, NOW, retention_days=30)
    second_run_count = purge_expired_media(db_session, NOW, retention_days=30)

    assert second_run_count == 0
    assert calls == ["media/f.mp4"]


# --- purge_expired_recordings ---


def test_purge_expired_recordings_removes_recording_and_related_rows(db_session, monkeypatch):
    import app.recording_deletion as recording_deletion

    monkeypatch.setattr(recording_deletion, "delete_media", lambda key: None)

    recording = _make_recording(db_session, NOW - timedelta(days=181))
    db_session.add(Message(recording_id=recording.id, role="user", content="вопрос"))
    db_session.add(ErrorLog(recording_id=recording.id, level="error", message="упс", context={}))
    db_session.commit()

    count = purge_expired_recordings(db_session, NOW, retention_days=180)

    assert count == 1
    assert db_session.get(Recording, recording.id) is None
    assert db_session.query(Message).filter_by(recording_id=recording.id).count() == 0
    assert db_session.query(ErrorLog).filter_by(recording_id=recording.id).count() == 0


def test_purge_expired_recordings_skips_recordings_within_retention(db_session, monkeypatch):
    import app.recording_deletion as recording_deletion

    monkeypatch.setattr(recording_deletion, "delete_media", lambda key: None)

    recording = _make_recording(db_session, NOW - timedelta(days=100))

    count = purge_expired_recordings(db_session, NOW, retention_days=180)

    assert count == 0
    assert db_session.get(Recording, recording.id) is not None


def test_purge_expired_recordings_is_idempotent(db_session, monkeypatch):
    import app.recording_deletion as recording_deletion

    monkeypatch.setattr(recording_deletion, "delete_media", lambda key: None)

    _make_recording(db_session, NOW - timedelta(days=181))

    first_count = purge_expired_recordings(db_session, NOW, retention_days=180)
    second_count = purge_expired_recordings(db_session, NOW, retention_days=180)

    assert first_count == 1
    assert second_count == 0


def test_purge_expired_recordings_calls_delete_media_even_if_already_media_purged(db_session, monkeypatch):
    # S3 delete_object on an already-missing key is a no-op success, so
    # calling it again here (rather than branching on media_deleted_at) is
    # deliberately simple and still safe.
    import app.recording_deletion as recording_deletion

    calls = []
    monkeypatch.setattr(recording_deletion, "delete_media", lambda key: calls.append(key))

    _make_recording(db_session, NOW - timedelta(days=181), media_deleted_at=NOW - timedelta(days=100))

    purge_expired_recordings(db_session, NOW, retention_days=180)

    assert calls == ["media/f.mp4"]


# --- run_retention ---


def test_run_retention_logs_a_summary(db_session, monkeypatch):
    import app.recording_deletion as recording_deletion
    import app.retention as retention

    monkeypatch.setattr(retention, "delete_media", lambda key: None)
    monkeypatch.setattr(recording_deletion, "delete_media", lambda key: None)

    _make_recording(db_session, NOW - timedelta(days=31))
    _make_recording(db_session, NOW - timedelta(days=181))

    run_retention(db_session, NOW)

    summary_logs = db_session.query(ErrorLog).filter_by(recording_id=None, level="info").all()
    assert len(summary_logs) == 1
    # both recordings are older than media_retention_days (30), so both get
    # their media purged; only the 181-day-old one also exceeds
    # data_retention_days (180) and gets deleted entirely
    assert summary_logs[0].context["media_purged"] == 2
    assert summary_logs[0].context["recordings_purged"] == 1
