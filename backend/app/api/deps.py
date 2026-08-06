from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth import InvalidTokenError, decode_access_token
from app.db import get_db
from app.models import User


def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="требуется авторизация")

    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_access_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="недействительный токен") from exc

    user = db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="пользователь не найден")
    return user


def get_active_user(user: User = Depends(get_current_user)) -> User:
    if user.status == "blocked":
        raise HTTPException(status_code=403, detail="доступ заблокирован")
    if user.status == "pending":
        raise HTTPException(status_code=403, detail="аккаунт ожидает одобрения администратором")
    return user


def get_admin_user(user: User = Depends(get_active_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="только для администраторов")
    return user
