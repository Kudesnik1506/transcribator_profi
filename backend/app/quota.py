from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import Recording

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
