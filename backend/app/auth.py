from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User

JWT_ALGORITHM = "HS256"


class InvalidTokenError(RuntimeError):
    pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: str, expires_minutes: int | None = None) -> str:
    minutes = settings.jwt_expires_minutes if expires_minutes is None else expires_minutes
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": user_id, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc


def bootstrap_admin_user(db: Session, email: str, password: str) -> None:
    """Create the first Administrator from deploy-time env vars, if one doesn't exist yet.

    Registration always creates a pending regular user, so this is the only
    way a fresh deployment gets an Administrator able to approve anyone else.
    """
    if not email or not password:
        return
    if db.query(User).filter_by(email=email).first():
        return
    db.add(User(email=email, password_hash=hash_password(password), role="admin", status="active"))
    db.commit()
