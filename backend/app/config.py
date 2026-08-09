from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/transcribator"
    redis_url: str = "redis://localhost:6379"

    s3_endpoint_url: str = "https://s3.timeweb.cloud"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "transcribator"
    s3_region: str = "ru-1"

    max_upload_size_bytes: int = 2 * 1024**3
    multipart_part_size_bytes: int = 16 * 1024**2
    # Ticket screenshots — single-shot presigned PUT, not multipart.
    max_screenshot_size_bytes: int = 10 * 1024**2

    yandex_api_key: str = ""
    yandex_folder_id: str = ""

    timeweb_ai_gateway_key: str = ""
    timeweb_ai_gateway_url: str = "https://api.timeweb.ai/v1"
    timeweb_ai_gateway_model: str = "gpt-4o-mini"
    max_dialog_context_tokens: int = 100_000

    # Must be a real random secret in production — this default is dev-only
    # and intentionally obvious so it's never mistaken for a real value.
    jwt_secret_key: str = "insecure-dev-secret-change-me"
    jwt_expires_minutes: int = 60 * 24 * 7

    # If set, an admin user is created at startup if one with this email
    # doesn't exist yet — the only way to get a first Administrator in,
    # since registration always creates a pending regular user.
    admin_email: str = ""
    admin_password: str = ""

    # "fast" (~30 min, full price) or "deferred" (up to 24h, ~4x cheaper).
    # The frontend reads this via GET /config so changing it here changes
    # the pre-selected radio too — no frontend code change needed (D15).
    default_processing_mode: str = "deferred"

    # Second safety net after moderation: caps spend even from an already-
    # approved user who starts uploading in bulk. Calendar day, MSK.
    daily_upload_quota: int = 3

    # Used to build the direct link to a Recording's result page in
    # notification emails/Telegram messages (D17).
    frontend_base_url: str = "http://localhost:3000"

    # Empty smtp_host means "not configured" — notify.py treats that as a
    # delivery failure to log, not a crash (D17, real credentials are open
    # question #1 in docs/spec.md, still pending from the customer).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@example.com"

    # Same "empty means not configured" contract as SMTP above.
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    # Set via Telegram's setWebhook `secret_token` param and checked against
    # the X-Telegram-Bot-Api-Secret-Token header — without it, anyone who
    # guesses a live link code could steal it by hitting our webhook first.
    # Empty means "not configured", so the check is skipped (dev/no bot yet).
    telegram_webhook_secret: str = ""
    # Chat ID that gets pinged when a user files a new support ticket.
    # Independent of a user's own telegram_chat_id — that column was for
    # per-user recording notifications, which the profile page no longer
    # exposes; this is a fixed operator channel, set once in .env.
    admin_telegram_chat_id: str = ""

    # Two different clocks (D6): media is the expensive part (terabytes at
    # scale), text artifacts (Транскрипт/Сводка/Диалог) cost pennies to keep.
    media_retention_days: int = 30
    data_retention_days: int = 180
    # Activity log: who did what, when — for diagnosing tickets and security
    # review. Shorter horizon than data_retention_days on purpose — it's
    # operational telemetry, not user content, so it needn't outlive it.
    activity_retention_days: int = 90


settings = Settings()
