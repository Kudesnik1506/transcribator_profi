from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user
from app.db import get_db
from app.models import ErrorLog, Message, Recording, User
from app.s3 import delete_media

router = APIRouter(prefix="/admin", dependencies=[Depends(get_admin_user)])


class AdminUserResponse(BaseModel):
    id: str
    email: str
    role: str
    status: str
    created_at: datetime


def _user_response(user: User) -> AdminUserResponse:
    return AdminUserResponse(id=user.id, email=user.email, role=user.role, status=user.status, created_at=user.created_at)


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(db: Session = Depends(get_db)) -> list[AdminUserResponse]:
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [_user_response(u) for u in users]


def _get_user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="пользователь не найден")
    return user


@router.post("/users/{user_id}/approve", response_model=AdminUserResponse)
def approve_user(user_id: str, db: Session = Depends(get_db)) -> AdminUserResponse:
    user = _get_user_or_404(db, user_id)
    user.status = "active"
    db.commit()
    return _user_response(user)


@router.post("/users/{user_id}/block", response_model=AdminUserResponse)
def block_user(
    user_id: str, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)
) -> AdminUserResponse:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="нельзя заблокировать самого себя")
    user = _get_user_or_404(db, user_id)
    user.status = "blocked"
    db.commit()
    return _user_response(user)


class AdminRecordingResponse(BaseModel):
    id: str
    original_filename: str
    status: str
    mode: str
    progress_percent: int
    user_id: str | None
    user_email: str | None
    created_at: datetime


@router.get("/recordings", response_model=list[AdminRecordingResponse])
def list_all_recordings(
    user_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list[AdminRecordingResponse]:
    query = db.query(Recording).order_by(Recording.created_at.desc())
    if user_id:
        query = query.filter(Recording.user_id == user_id)
    if status:
        query = query.filter(Recording.status == status)

    recordings = query.all()
    users_by_id = {u.id: u for u in db.query(User).all()}

    return [
        AdminRecordingResponse(
            id=r.id,
            original_filename=r.original_filename,
            status=r.status,
            mode=r.mode,
            progress_percent=r.progress_percent,
            user_id=r.user_id,
            user_email=users_by_id[r.user_id].email if r.user_id in users_by_id else None,
            created_at=r.created_at,
        )
        for r in recordings
    ]


@router.delete("/recordings/{recording_id}", status_code=204)
def delete_recording(recording_id: str, db: Session = Depends(get_db)) -> None:
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="запись не найдена")

    delete_media(recording.s3_key_media)

    db.query(Message).filter_by(recording_id=recording.id).delete()
    db.query(ErrorLog).filter_by(recording_id=recording.id).delete()
    db.delete(recording)
    db.commit()


class AdminErrorLogResponse(BaseModel):
    id: str
    recording_id: str | None
    level: str
    message: str
    context: dict
    created_at: datetime


@router.get("/error-logs", response_model=list[AdminErrorLogResponse])
def list_error_logs(
    level: str | None = None,
    recording_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[AdminErrorLogResponse]:
    query = db.query(ErrorLog).order_by(ErrorLog.created_at.desc())
    if level:
        query = query.filter(ErrorLog.level == level)
    if recording_id:
        query = query.filter(ErrorLog.recording_id == recording_id)

    logs = query.all()
    return [
        AdminErrorLogResponse(
            id=log.id,
            recording_id=log.recording_id,
            level=log.level,
            message=log.message,
            context=log.context,
            created_at=log.created_at,
        )
        for log in logs
    ]
