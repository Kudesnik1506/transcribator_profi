from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Recording, User

# No DST in Russia since 2014, so a fixed UTC+3 offset is always correct.
MSK = timezone(timedelta(hours=3))


def _start_of_msk_day(now_utc: datetime) -> datetime:
    start_of_day_msk = now_utc.astimezone(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
    return start_of_day_msk.astimezone(timezone.utc)


def uploads_today(db: Session, user_id: str, now_utc: datetime) -> int:
    start = _start_of_msk_day(now_utc)
    return (
        db.query(Recording)
        .filter(
            Recording.user_id == user_id,
            Recording.status != "failed",
            Recording.created_at >= start,
        )
        .count()
    )


def next_reset_at(now_utc: datetime) -> datetime:
    return _start_of_msk_day(now_utc) + timedelta(days=1)


def quota_exceeded_message(quota: int, now_utc: datetime) -> str:
    reset_msk = next_reset_at(now_utc).astimezone(MSK)
    return (
        f"Достигнут дневной лимит в {quota} записи. "
        f"Квота обновится в {reset_msk.strftime('%H:%M')} по московскому времени."
    )


def enforce_daily_quota(db: Session, user: User, now_utc: datetime) -> None:
    """Reject with 429 once the user has hit their daily upload quota.

    Called both before a multipart upload starts (so a user over quota
    doesn't waste time/bandwidth uploading a file) and again when the
    Recording row is created (closing the TOCTOU gap a long upload leaves
    open).
    """
    if user.role == "admin":
        return
    if uploads_today(db, user.id, now_utc) >= settings.daily_upload_quota:
        raise HTTPException(
            status_code=429,
            detail=quota_exceeded_message(settings.daily_upload_quota, now_utc),
        )
