from sqlalchemy.orm import Session

from app.models import ErrorLog


def log_error(
    db: Session, recording_id: str | None, message: str, context: dict | None = None, level: str = "error"
) -> None:
    db.add(ErrorLog(recording_id=recording_id, level=level, message=message, context=context or {}))
    db.commit()
