import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_active_user
from app.config import settings
from app.db import get_db
from app.models import TelegramLinkCode, User
from app.worker.notify import TelegramDeliveryError, send_telegram_text

router = APIRouter()

LINK_CODE_TTL_MINUTES = 15


class LinkCodeResponse(BaseModel):
    code: str
    bot_username: str
    expires_at: datetime


@router.post("/telegram/link-code", response_model=LinkCodeResponse)
def create_link_code(db: Session = Depends(get_db), user: User = Depends(get_active_user)) -> LinkCodeResponse:
    db.query(TelegramLinkCode).filter_by(user_id=user.id).delete()

    code = secrets.token_urlsafe(6)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=LINK_CODE_TTL_MINUTES)
    db.add(TelegramLinkCode(user_id=user.id, code=code, expires_at=expires_at))
    db.commit()

    return LinkCodeResponse(code=code, bot_username=settings.telegram_bot_username, expires_at=expires_at)


def _reply(chat_id: int, text: str) -> None:
    try:
        send_telegram_text(str(chat_id), text)
    except TelegramDeliveryError:
        pass


@router.post("/telegram/webhook")
def telegram_webhook(
    update: dict,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat_id = message.get("chat", {}).get("id")

    if chat_id is None or not text.startswith("/start"):
        return {"ok": True}

    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        _reply(chat_id, "Отправьте код привязки ссылкой из личного кабинета.")
        return {"ok": True}

    code = parts[1].strip()
    link = (
        db.query(TelegramLinkCode)
        .filter_by(code=code)
        .filter(TelegramLinkCode.expires_at > datetime.now(timezone.utc))
        .first()
    )
    if link is None:
        _reply(chat_id, "Код недействителен или устарел. Запросите новый в личном кабинете.")
        return {"ok": True}

    user = db.get(User, link.user_id)
    user.telegram_chat_id = str(chat_id)
    db.delete(link)
    db.commit()

    _reply(chat_id, "Telegram успешно привязан. Уведомления о готовых записях будут приходить сюда.")
    return {"ok": True}
