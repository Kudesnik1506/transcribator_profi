import smtplib

import httpx
import pytest
import respx

from app.worker.notify import (
    EmailDeliveryError,
    TelegramDeliveryError,
    build_notification_text,
    send_email,
    send_telegram_text,
)


def test_build_notification_text_includes_filename_status_and_link(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "frontend_base_url", "https://transcribator.example")

    text = build_notification_text("совещание.mp4", "done", "rec-1")

    assert "совещание.mp4" in text
    assert "готова" in text
    assert "https://transcribator.example/recordings/rec-1" in text


def test_build_notification_text_labels_partial_and_failed():
    assert "частично" in build_notification_text("f.mp4", "partial", "rec-1")
    assert "не удал" in build_notification_text("f.mp4", "failed", "rec-1")


def test_send_email_raises_when_smtp_not_configured(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "smtp_host", "")

    with pytest.raises(EmailDeliveryError):
        send_email("user@example.com", "f.mp4", "done", "rec-1")


def test_send_email_sends_via_smtp(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "bot@example.com")
    monkeypatch.setattr(settings, "smtp_password", "secret")
    monkeypatch.setattr(settings, "smtp_from", "bot@example.com")

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            sent["starttls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, message):
            sent["message"] = message

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    send_email("user@example.com", "f.mp4", "done", "rec-1")

    assert sent["host"] == "smtp.example.com"
    assert sent["login"] == ("bot@example.com", "secret")
    assert sent["message"]["To"] == "user@example.com"
    assert "f.mp4" in sent["message"]["Subject"]


def test_send_email_wraps_smtp_errors(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")

    class FailingSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            raise ConnectionRefusedError("no route to host")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(smtplib, "SMTP", FailingSMTP)

    with pytest.raises(EmailDeliveryError):
        send_email("user@example.com", "f.mp4", "done", "rec-1")


def test_send_telegram_text_raises_when_bot_not_configured(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "")

    with pytest.raises(TelegramDeliveryError):
        send_telegram_text("12345", "привет")


@respx.mock
def test_send_telegram_text_posts_to_bot_api(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "TESTTOKEN")

    route = respx.post("https://api.telegram.org/botTESTTOKEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    send_telegram_text("12345", "привет")

    assert route.called
    import json

    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body == {"chat_id": "12345", "text": "привет"}


@respx.mock
def test_send_telegram_text_raises_on_http_error(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "TESTTOKEN")

    respx.post("https://api.telegram.org/botTESTTOKEN/sendMessage").mock(
        return_value=httpx.Response(400, json={"ok": False, "description": "chat not found"})
    )

    with pytest.raises(TelegramDeliveryError):
        send_telegram_text("12345", "привет")
