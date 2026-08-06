import tempfile
from pathlib import Path

from arq.connections import RedisSettings

from app.config import settings as app_settings
from app.db import SessionLocal
from app.worker.tasks import process_recording


async def process_recording_job(ctx, recording_id: str) -> None:
    db = SessionLocal()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            process_recording(db, recording_id, work_dir=Path(tmp))
    finally:
        db.close()


class WorkerSettings:
    functions = [process_recording_job]
    redis_settings = RedisSettings.from_dsn(app_settings.redis_url)
