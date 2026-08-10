import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.activity_log import log_activity
from app.api.deps import get_current_user
from app.auth import create_access_token, hash_password, verify_password
from app.config import settings
from app.db import get_db
from app.models import ActivityLog, Recording, RecordingShare, TelegramLinkCode, User
from app.recording_deletion import purge_recording

router = APIRouter()

MIN_PASSWORD_LENGTH = 8
# bcrypt silently truncates input past 72 bytes — anything longer would let
# two different passwords sharing a 72-byte prefix hash identically.
MAX_PASSWORD_BYTES = 72


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail=f"пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise HTTPException(status_code=422, detail="пароль слишком длинный")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterResponse(BaseModel):
    id: str
    status: str


@router.post("/auth/register", response_model=RegisterResponse, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> RegisterResponse:
    validate_password(payload.password)

    existing = db.query(User).filter_by(email=payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="пользователь с таким email уже существует")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="user",
        status="pending",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_activity(db, user.id, "register", {"email": user.email}, request)

    return RegisterResponse(id=user.id, status=user.status)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter_by(email=payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="неверный email или пароль")
    if user.status == "blocked":
        raise HTTPException(status_code=403, detail="доступ заблокирован")

    log_activity(db, user.id, "login", {}, request)

    return LoginResponse(access_token=create_access_token(user.id))


class MeResponse(BaseModel):
    id: str
    email: str
    role: str
    status: str
    telegram_linked: bool


@router.get("/auth/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        status=user.status,
        telegram_linked=user.telegram_chat_id is not None,
    )


@router.delete("/auth/me", status_code=204)
def delete_me(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    log_activity(db, user.id, "delete_account", {}, request)

    recordings = db.query(Recording).filter_by(user_id=user.id).all()
    for recording in recordings:
        purge_recording(db, recording)

    db.query(RecordingShare).filter_by(shared_with_user_id=user.id).delete()
    db.query(TelegramLinkCode).filter_by(user_id=user.id).delete()
    # Anonymize rather than delete — keeps aggregate activity history
    # accurate without retaining a link to the now-gone account.
    db.query(ActivityLog).filter_by(user_id=user.id).update({"user_id": None})
    db.delete(user)
    db.commit()


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.patch("/auth/me/password", status_code=204)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="неверный текущий пароль")
    validate_password(payload.new_password)

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    log_activity(db, user.id, "password_changed", {}, request)


class EmergencyResetRequest(BaseModel):
    email: EmailStr
    new_password: str


# Account-recovery path for when no one can sign in — e.g. the only
# Administrator forgot their password. Authenticated by a static secret
# (EMERGENCY_RESET_TOKEN in .env) instead of a session, since a session is
# exactly what's unavailable here. Same 404 whether the feature is off,
# the token is wrong, or the email doesn't exist — an attacker probing this
# endpoint shouldn't learn which case they hit.
@router.post("/auth/emergency-reset", status_code=204)
def emergency_reset_password(
    payload: EmergencyResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    x_reset_token: str | None = Header(default=None),
) -> None:
    if not settings.emergency_reset_token or not x_reset_token:
        raise HTTPException(status_code=404)
    if not secrets.compare_digest(x_reset_token, settings.emergency_reset_token):
        raise HTTPException(status_code=404)

    user = db.query(User).filter_by(email=payload.email).first()
    if user is None:
        raise HTTPException(status_code=404)
    validate_password(payload.new_password)

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    log_activity(db, user.id, "emergency_password_reset", {}, request)
