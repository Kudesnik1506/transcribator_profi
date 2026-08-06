from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Recording, Segment, Summary
from app.s3 import download_media
from app.worker.ai_gateway_client import summarize
from app.worker.ffmpeg_extract import extract_audio
from app.worker.speechkit_client import transcribe


def process_recording(db: Session, recording_id: str, work_dir: Path) -> None:
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise ValueError(f"recording {recording_id} not found")

    try:
        media_path = work_dir / "media"
        audio_path = work_dir / "audio.ogg"

        recording.status = "extracting"
        db.commit()
        download_media(recording.s3_key_media, media_path)
        extract_audio(media_path, audio_path)

        recording.status = "transcribing"
        db.commit()
        audio_bytes = audio_path.read_bytes()
        segments = transcribe(audio_bytes)
        for seg in segments:
            db.add(Segment(recording_id=recording.id, start_ms=seg.start_ms, end_ms=seg.end_ms, text=seg.text))
        db.commit()

        recording.status = "summarizing"
        db.commit()
        transcript_text = "\n".join(seg.text for seg in segments)
        items = summarize(transcript_text)
        db.add(Summary(recording_id=recording.id, items=items, model=settings.timeweb_ai_gateway_model))

        recording.status = "done"
        db.commit()
    except Exception as exc:
        recording.status = "failed"
        recording.error_message = str(exc)
        db.commit()
        raise
