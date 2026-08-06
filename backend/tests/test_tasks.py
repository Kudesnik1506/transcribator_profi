from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.db import Base
from app.models import Chunk, ErrorLog, Recording, Segment, Summary
from app.worker import tasks
from app.worker.ffmpeg_extract import AudioChunk
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


def _fake_chunks(work_dir: Path, n: int) -> list[AudioChunk]:
    chunks = []
    for i in range(n):
        path = work_dir / f"chunk_{i}.ogg"
        path.write_bytes(b"fake-chunk-audio")
        chunks.append(AudioChunk(idx=i, start_sec=i * 900.0, end_sec=(i + 1) * 900.0, path=path))
    return chunks


def _setup_common_mocks(monkeypatch, chunks):
    monkeypatch.setattr(tasks, "download_media", lambda s3_key, dest: dest.write_bytes(b"fake-media"))
    monkeypatch.setattr(
        tasks, "extract_audio", lambda media_path, audio_path: audio_path.write_bytes(b"fake-audio")
    )
    monkeypatch.setattr(
        tasks, "split_audio_into_chunks", lambda audio_path, output_dir, chunk_duration_sec: chunks
    )
    monkeypatch.setattr(tasks, "sleep", lambda s: None)


def _make_recording(db_session) -> Recording:
    recording = Recording(original_filename="m.mp4", s3_key_media="media/m.mp4", status="queued")
    db_session.add(recording)
    db_session.commit()
    return recording


def test_process_recording_all_chunks_succeed(db_session, tmp_path, monkeypatch):
    recording = _make_recording(db_session)
    chunks = _fake_chunks(tmp_path, 2)
    _setup_common_mocks(monkeypatch, chunks)
    monkeypatch.setattr(
        tasks, "transcribe", lambda audio_bytes: [SpeechKitSegment(start_ms=0, end_ms=1000, text="привет")]
    )
    monkeypatch.setattr(tasks, "summarize", lambda transcript: ["пункт"])

    tasks.process_recording(db_session, recording.id, work_dir=tmp_path)

    db_session.refresh(recording)
    assert recording.status == "done"
    assert recording.progress_percent == 100

    segments = db_session.query(Segment).filter_by(recording_id=recording.id).order_by(Segment.start_ms).all()
    assert len(segments) == 2
    assert segments[0].start_ms == 0
    assert segments[1].start_ms == 900_000

    chunk_rows = db_session.query(Chunk).filter_by(recording_id=recording.id).order_by(Chunk.idx).all()
    assert [c.status for c in chunk_rows] == ["done", "done"]

    summary = db_session.query(Summary).filter_by(recording_id=recording.id).one()
    assert summary.items == ["пункт"]


def test_process_recording_partial_when_some_chunks_fail_after_retries(db_session, tmp_path, monkeypatch):
    recording = _make_recording(db_session)
    chunks = _fake_chunks(tmp_path, 2)
    _setup_common_mocks(monkeypatch, chunks)

    calls = {"n": 0}

    def transcribe_side_effect(audio_bytes):
        calls["n"] += 1
        if calls["n"] == 1:
            return [SpeechKitSegment(start_ms=0, end_ms=1000, text="ok")]
        raise RuntimeError("speechkit boom")

    monkeypatch.setattr(tasks, "transcribe", transcribe_side_effect)
    monkeypatch.setattr(tasks, "summarize", lambda transcript: ["частичная сводка"])

    tasks.process_recording(db_session, recording.id, work_dir=tmp_path)

    db_session.refresh(recording)
    assert recording.status == "partial"
    assert recording.progress_percent == 100

    chunk_rows = db_session.query(Chunk).filter_by(recording_id=recording.id).order_by(Chunk.idx).all()
    assert chunk_rows[0].status == "done"
    assert chunk_rows[1].status == "failed"
    assert chunk_rows[1].attempts == 3

    segments = db_session.query(Segment).filter_by(recording_id=recording.id).all()
    assert len(segments) == 1

    error_logs = db_session.query(ErrorLog).filter_by(recording_id=recording.id).all()
    assert len(error_logs) == 1
    assert str(chunk_rows[1].idx) in error_logs[0].message or "chunk" in error_logs[0].message.lower()

    summary = db_session.query(Summary).filter_by(recording_id=recording.id).one()
    assert summary.items == ["частичная сводка"]


def test_process_recording_failed_when_all_chunks_fail(db_session, tmp_path, monkeypatch):
    recording = _make_recording(db_session)
    chunks = _fake_chunks(tmp_path, 1)
    _setup_common_mocks(monkeypatch, chunks)

    def always_fail(audio_bytes):
        raise RuntimeError("speechkit boom")

    monkeypatch.setattr(tasks, "transcribe", always_fail)
    monkeypatch.setattr(tasks, "summarize", lambda transcript: ["should not be called"])

    tasks.process_recording(db_session, recording.id, work_dir=tmp_path)

    db_session.refresh(recording)
    assert recording.status == "failed"
    assert recording.error_message

    assert db_session.query(Summary).filter_by(recording_id=recording.id).first() is None


def test_retry_failed_chunks_reprocesses_only_failed_ones(db_session, tmp_path, monkeypatch):
    recording = _make_recording(db_session)
    chunk0 = Chunk(recording_id=recording.id, idx=0, start_sec=0, end_sec=900, status="done", attempts=1)
    chunk1 = Chunk(recording_id=recording.id, idx=1, start_sec=900, end_sec=1800, status="failed", attempts=3)
    db_session.add_all([chunk0, chunk1])
    db_session.add(
        Segment(recording_id=recording.id, chunk_id=chunk0.id, start_ms=0, end_ms=1000, text="успешный")
    )
    recording.status = "partial"
    recording.progress_percent = 100
    db_session.commit()

    chunks = _fake_chunks(tmp_path, 2)
    _setup_common_mocks(monkeypatch, chunks)
    monkeypatch.setattr(
        tasks,
        "transcribe",
        lambda audio_bytes: [SpeechKitSegment(start_ms=0, end_ms=500, text="восстановлено")],
    )
    monkeypatch.setattr(tasks, "summarize", lambda transcript: ["новая сводка"])

    tasks.retry_failed_chunks(db_session, recording.id, work_dir=tmp_path)

    db_session.refresh(recording)
    assert recording.status == "done"

    db_session.refresh(chunk0)
    db_session.refresh(chunk1)
    assert chunk0.status == "done"
    assert chunk0.attempts == 1
    assert chunk1.status == "done"
    assert chunk1.attempts == 1

    segments = db_session.query(Segment).filter_by(recording_id=recording.id).order_by(Segment.start_ms).all()
    assert len(segments) == 2
    assert segments[0].text == "успешный"
    assert segments[1].text == "восстановлено"
    assert segments[1].start_ms == 900_000


def test_retry_failed_chunks_noop_when_nothing_failed(db_session, tmp_path, monkeypatch):
    recording = _make_recording(db_session)
    chunk0 = Chunk(recording_id=recording.id, idx=0, start_sec=0, end_sec=900, status="done", attempts=1)
    db_session.add(chunk0)
    recording.status = "done"
    db_session.commit()

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("should not be called when nothing failed")

    monkeypatch.setattr(tasks, "download_media", must_not_be_called)

    tasks.retry_failed_chunks(db_session, recording.id, work_dir=tmp_path)

    db_session.refresh(recording)
    assert recording.status == "done"


def test_process_recording_marks_failed_on_download_exception(db_session, tmp_path, monkeypatch):
    recording = _make_recording(db_session)

    def boom(*args, **kwargs):
        raise RuntimeError("s3 is down")

    monkeypatch.setattr(tasks, "download_media", boom)

    with pytest.raises(RuntimeError):
        tasks.process_recording(db_session, recording.id, work_dir=tmp_path)

    db_session.refresh(recording)
    assert recording.status == "failed"
    assert "s3 is down" in recording.error_message


def test_process_recording_writes_error_log_on_pipeline_failure(db_session, tmp_path, monkeypatch):
    recording = _make_recording(db_session)

    def boom(*args, **kwargs):
        raise RuntimeError("s3 is down")

    monkeypatch.setattr(tasks, "download_media", boom)

    with pytest.raises(RuntimeError):
        tasks.process_recording(db_session, recording.id, work_dir=tmp_path)

    error_logs = db_session.query(ErrorLog).filter_by(recording_id=recording.id).all()
    assert len(error_logs) == 1
    assert "s3 is down" in error_logs[0].message


def test_process_recording_sets_summarizing_status_before_generating_summary(db_session, tmp_path, monkeypatch):
    recording = _make_recording(db_session)
    chunks = _fake_chunks(tmp_path, 1)
    _setup_common_mocks(monkeypatch, chunks)
    monkeypatch.setattr(
        tasks, "transcribe", lambda audio_bytes: [SpeechKitSegment(start_ms=0, end_ms=1000, text="ok")]
    )

    observed = {}

    def capture_status(transcript):
        observed["status"] = recording.status
        return ["пункт"]

    monkeypatch.setattr(tasks, "summarize", capture_status)

    tasks.process_recording(db_session, recording.id, work_dir=tmp_path)

    assert observed["status"] == "summarizing"


def test_retry_failed_chunks_updates_existing_summary_instead_of_duplicating(db_session, tmp_path, monkeypatch):
    recording = _make_recording(db_session)
    chunk0 = Chunk(recording_id=recording.id, idx=0, start_sec=0, end_sec=900, status="done", attempts=1)
    chunk1 = Chunk(recording_id=recording.id, idx=1, start_sec=900, end_sec=1800, status="failed", attempts=3)
    db_session.add_all([chunk0, chunk1])
    db_session.add(
        Segment(recording_id=recording.id, chunk_id=chunk0.id, start_ms=0, end_ms=1000, text="успешный")
    )
    db_session.add(Summary(recording_id=recording.id, items=["старая сводка"], model="gpt-4o-mini"))
    recording.status = "partial"
    db_session.commit()

    chunks = _fake_chunks(tmp_path, 2)
    _setup_common_mocks(monkeypatch, chunks)
    monkeypatch.setattr(
        tasks,
        "transcribe",
        lambda audio_bytes: [SpeechKitSegment(start_ms=0, end_ms=500, text="восстановлено")],
    )
    monkeypatch.setattr(tasks, "summarize", lambda transcript: ["новая сводка"])

    tasks.retry_failed_chunks(db_session, recording.id, work_dir=tmp_path)

    summaries = db_session.query(Summary).filter_by(recording_id=recording.id).all()
    assert len(summaries) == 1
    assert summaries[0].items == ["новая сводка"]
