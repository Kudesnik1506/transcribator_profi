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

    yandex_api_key: str = ""
    yandex_folder_id: str = ""

    timeweb_ai_gateway_key: str = ""
    timeweb_ai_gateway_url: str = "https://api.timeweb.ai/v1"
    timeweb_ai_gateway_model: str = "gpt-4o-mini"
    max_dialog_context_tokens: int = 100_000


settings = Settings()
