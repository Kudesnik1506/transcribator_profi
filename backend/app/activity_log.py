from fastapi import Request
from sqlalchemy.orm import Session

from app.models import ActivityLog


def log_activity(
    db: Session,
    user_id: str | None,
    action: str,
    context: dict | None = None,
    request: Request | None = None,
) -> None:
    ip = request.client.host if request and request.client else None
    user_agent = request.headers.get("user-agent") if request else None
    db.add(
        ActivityLog(
            user_id=user_id,
            action=action,
            context=context or {},
            ip=ip,
            user_agent=user_agent,
        )
    )
    db.commit()
