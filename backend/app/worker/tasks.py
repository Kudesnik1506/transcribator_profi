from pathlib import Path
from time import sleep

from sqlalchemy.orm import Session

from app.config import settings
from app.error_log import log_error
from app.models import Chunk, Recording, Segment, Summary
from app.s3 import download_media
from app.worker.ai_gateway_client import summarize
from app.worker.ffmpeg_extract import AudioChunk, extract_audio, split_audio_into_chunks
from app.worker.notify import notify_recording_finished
from app.worker.retry import retry_with_backoff
from app.worker.speechkit_client import model_for_mode, poll_config_for_mode, transcribe
from app.worker.timecodes import offset_segments

CHUNK_DURATION_SEC = 900
MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SEC = 5.0


def process_recording(db: Session, recording_id: str, work_dir: Path) -> None:
    recording = _get_recording_or_raise(db, recording_id)

    try:
        recording.status = "extracting"
        db.commit()
        audio_chunks = _prepare_audio(recording, work_dir)

        chunk_rows: list[Chunk] = []
        for audio_chunk in audio_chunks:
            chunk_row = Chunk(
                recording_id=recording.id,
                idx=audio_chunk.idx,
                start_sec=audio_chunk.start_sec,
                end_sec=audio_chunk.end_sec,
                status="pending",
            )
            db.add(chunk_row)
            chunk_rows.append(chunk_row)
        db.commit()

        recording.status = "transcribing"
        db.commit()

        for chunk_row, audio_chunk in zip(chunk_rows, audio_chunks):
            _process_chunk(db, recording, chunk_row, audio_chunk)
            recording.progress_percent = _progress_percent(chunk_rows)
            db.commit()

        _finalize(db, recording, chunk_rows)
    except Exception as exc:
        _mark_failed(db, recording, exc)
        raise


def retry_failed_chunks(db: Session, recording_id: str, work_dir: Path) -> None:
    recording = _get_recording_or_raise(db, recording_id)

    failed_chunks = (
        db.query(Chunk).filter_by(recording_id=recording.id, status="failed").order_by(Chunk.idx).all()
    )
    if not failed_chunks:
        return

    try:
        audio_chunks_by_idx = {c.idx: c for c in _prepare_audio(recording, work_dir)}

        recording.status = "transcribing"
        db.commit()

        all_chunk_rows = db.query(Chunk).filter_by(recording_id=recording.id).order_by(Chunk.idx).all()

        for chunk_row in failed_chunks:
            audio_chunk = audio_chunks_by_idx.get(chunk_row.idx)
            if audio_chunk is None:
                continue
            chunk_row.attempts = 0
            _process_chunk(db, recording, chunk_row, audio_chunk)
            recording.progress_percent = _progress_percent(all_chunk_rows)
            db.commit()

        _finalize(db, recording, all_chunk_rows)
    except Exception as exc:
        _mark_failed(db, recording, exc)
        raise


def _get_recording_or_raise(db: Session, recording_id: str) -> Recording:
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise ValueError(f"recording {recording_id} not found")
    return recording


def _prepare_audio(recording: Recording, work_dir: Path) -> list[AudioChunk]:
    media_path = work_dir / "media"
    audio_path = work_dir / "audio.ogg"
    chunks_dir = work_dir / "chunks"

    download_media(recording.s3_key_media, media_path)
    extract_audio(media_path, audio_path)
    return split_audio_into_chunks(audio_path, chunks_dir, CHUNK_DURATION_SEC)


def _process_chunk(db: Session, recording: Recording, chunk_row: Chunk, audio_chunk: AudioChunk) -> None:
    chunk_row.status = "processing"
    db.commit()

    def attempt() -> list:
        chunk_row.attempts += 1
        db.commit()
        audio_bytes = audio_chunk.path.read_bytes()
        poll_interval_sec, max_polls = poll_config_for_mode(recording.mode)
        return transcribe(
            audio_bytes,
            model=model_for_mode(recording.mode),
            poll_interval_sec=poll_interval_sec,
            max_polls=max_polls,
        )

    try:
        segments = retry_with_backoff(
            attempt, max_attempts=MAX_ATTEMPTS, base_delay_sec=RETRY_BASE_DELAY_SEC, sleep=sleep
        )
        for seg in offset_segments(segments, audio_chunk.start_sec):
            db.add(
                Segment(
                    recording_id=recording.id,
                    chunk_id=chunk_row.id,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                    text=seg.text,
                )
            )
        chunk_row.status = "done"
        db.commit()
    except Exception as exc:
        chunk_row.status = "failed"
        db.commit()
        log_error(
            db,
            recording.id,
            f"chunk {chunk_row.idx} failed after {chunk_row.attempts} attempts: {exc}",
            context={"chunk_id": chunk_row.id, "chunk_idx": chunk_row.idx},
        )


def _progress_percent(chunk_rows: list[Chunk]) -> int:
    total = len(chunk_rows)
    if total == 0:
        return 100
    finished = sum(1 for chunk_row in chunk_rows if chunk_row.status in ("done", "failed"))
    return round(finished / total * 100)


def _finalize(db: Session, recording: Recording, chunk_rows: list[Chunk]) -> None:
    statuses = [chunk_row.status for chunk_row in chunk_rows]
    all_failed = bool(statuses) and all(s == "failed" for s in statuses)
    any_failed = any(s == "failed" for s in statuses)

    if all_failed:
        recording.status = "failed"
        recording.error_message = "все куски не удалось распознать после повторных попыток"
        db.commit()
        log_error(db, recording.id, recording.error_message, context={"chunk_count": len(chunk_rows)})
        notify_recording_finished(db, recording)
        return

    segments = db.query(Segment).filter_by(recording_id=recording.id).order_by(Segment.start_ms).all()
    if segments:
        recording.status = "summarizing"
        db.commit()

        transcript_text = "\n".join(s.text for s in segments)
        items = summarize(transcript_text)

        existing_summary = db.query(Summary).filter_by(recording_id=recording.id).first()
        if existing_summary:
            existing_summary.items = items
            existing_summary.model = settings.timeweb_ai_gateway_model
        else:
            db.add(Summary(recording_id=recording.id, items=items, model=settings.timeweb_ai_gateway_model))

    recording.status = "partial" if any_failed else "done"
    db.commit()
    notify_recording_finished(db, recording)


def _mark_failed(db: Session, recording: Recording, exc: Exception) -> None:
    stage = recording.status
    recording.status = "failed"
    recording.error_message = str(exc)
    db.commit()
    log_error(db, recording.id, str(exc), context={"stage": stage})
    notify_recording_finished(db, recording)
