import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

import httpx

from app.config import settings
from app.error_log import log_error
from app.models import Recording, User

TELEGRAM_API_URL_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"

STATUS_LABELS = {
    "done": "готова",
    "partial": "обработана частично",
    "failed": "не удалась",
}


class EmailDeliveryError(RuntimeError):
    pass


class TelegramDeliveryError(RuntimeError):
    pass


def _recording_url(recording_id: str) -> str:
    return f"{settings.frontend_base_url}/recordings/{recording_id}"


def build_notification_text(original_filename: str, status: str, recording_id: str) -> str:
    label = STATUS_LABELS.get(status, status)
    return f"Запись «{original_filename}» {label}.\nОткрыть: {_recording_url(recording_id)}"


def send_email(to_address: str, original_filename: str, status: str, recording_id: str) -> None:
    if not settings.smtp_host:
        raise EmailDeliveryError("SMTP не настроен")

    message = EmailMessage()
    message["Subject"] = f"Запись «{original_filename}»: {STATUS_LABELS.get(status, status)}"
    message["From"] = settings.smtp_from
    message["To"] = to_address
    message.set_content(build_notification_text(original_filename, status, recording_id))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            client.starttls()
            if settings.smtp_user:
                client.login(settings.smtp_user, settings.smtp_password)
            client.send_message(message)
    except Exception as exc:
        raise EmailDeliveryError(str(exc)) from exc


def send_telegram_text(chat_id: str, text: str) -> None:
    if not settings.telegram_bot_token:
        raise TelegramDeliveryError("Telegram бот не настроен")

    url = TELEGRAM_API_URL_TEMPLATE.format(token=settings.telegram_bot_token)
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json={"chat_id": chat_id, "text": text})
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise TelegramDeliveryError(str(exc)) from exc


def send_telegram_message(chat_id: str, original_filename: str, status: str, recording_id: str) -> None:
    send_telegram_text(chat_id, build_notification_text(original_filename, status, recording_id))


def _deliver(db, recording: Recording, channel: str, send) -> None:
    try:
        send()
    except (EmailDeliveryError, TelegramDeliveryError) as exc:
        log_error(db, recording.id, f"{channel} notification failed: {exc}", context={"channel": channel})


def notify_recording_finished(db, recording: Recording) -> None:
    if recording.notified_at is not None and recording.notified_status == recording.status:
        return

    if recording.user_id is not None:
        user = db.get(User, recording.user_id)
        if user is not None:
            _deliver(
                db,
                recording,
                "email",
                lambda: send_email(user.email, recording.original_filename, recording.status, recording.id),
            )

            if user.telegram_chat_id:
                _deliver(
                    db,
                    recording,
                    "telegram",
                    lambda: send_telegram_message(
                        user.telegram_chat_id, recording.original_filename, recording.status, recording.id
                    ),
                )

    recording.notified_at = datetime.now(timezone.utc)
    recording.notified_status = recording.status
    db.commit()
