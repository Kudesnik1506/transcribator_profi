from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.error_log import log_error
from app.models import Recording
from app.recording_deletion import purge_recording
from app.s3 import delete_media

# Only recordings whose pipeline has actually finished — a recording still
# stuck in queued/extracting/transcribing shouldn't have its media pulled
# out from under a worker that might still be reading it.
_TERMINAL_STATUSES = ("done", "partial", "failed")


def purge_expired_media(db: Session, now_utc: datetime, retention_days: int) -> int:
    cutoff = now_utc - timedelta(days=retention_days)
    recordings = (
        db.query(Recording)
        .filter(
            Recording.media_deleted_at.is_(None),
            Recording.created_at < cutoff,
            Recording.status.in_(_TERMINAL_STATUSES),
        )
        .all()
    )

    for recording in recordings:
        delete_media(recording.s3_key_media)
        recording.media_deleted_at = now_utc
    db.commit()

    return len(recordings)


def purge_expired_recordings(db: Session, now_utc: datetime, retention_days: int) -> int:
    cutoff = now_utc - timedelta(days=retention_days)
    recordings = db.query(Recording).filter(Recording.created_at < cutoff).all()

    for recording in recordings:
        purge_recording(db, recording)

    return len(recordings)


def run_retention(
    db: Session,
    now_utc: datetime,
    media_retention_days: int | None = None,
    data_retention_days: int | None = None,
) -> None:
    media_purged = purge_expired_media(db, now_utc, media_retention_days or settings.media_retention_days)
    recordings_purged = purge_expired_recordings(db, now_utc, data_retention_days or settings.data_retention_days)

    log_error(
        db,
        None,
        f"ретеншн: удалено медиа у {media_purged} Записей, удалено целиком {recordings_purged} Записей",
        context={"media_purged": media_purged, "recordings_purged": recordings_purged},
        level="info",
    )
