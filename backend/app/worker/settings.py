import tempfile
from datetime import datetime, timezone
from pathlib import Path

from arq.connections import RedisSettings
from arq.cron import cron

from app.config import settings as app_settings
from app.db import SessionLocal
from app.retention import run_retention
from app.worker.tasks import process_recording, retry_failed_chunks


async def process_recording_job(ctx, recording_id: str) -> None:
    db = SessionLocal()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            process_recording(db, recording_id, work_dir=Path(tmp))
    finally:
        db.close()


async def retry_failed_chunks_job(ctx, recording_id: str) -> None:
    db = SessionLocal()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            retry_failed_chunks(db, recording_id, work_dir=Path(tmp))
    finally:
        db.close()


async def run_retention_job(ctx) -> None:
    db = SessionLocal()
    try:
        run_retention(db, datetime.now(timezone.utc))
    finally:
        db.close()


class WorkerSettings:
    functions = [process_recording_job, retry_failed_chunks_job]
    # Server clock is UTC in the Docker containers (D1: Timeweb Moscow, but
    # the base image doesn't set TZ) — 03:00 UTC is 06:00 MSK, off-peak.
    cron_jobs = [cron(run_retention_job, hour=3, minute=0)]
    redis_settings = RedisSettings.from_dsn(app_settings.redis_url)
