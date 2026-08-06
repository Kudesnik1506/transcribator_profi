from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.db import Base
from app.models import Recording
from app.quota import next_reset_at, uploads_today

# 2026-08-06 12:00 MSK == 2026-08-06 09:00 UTC
NOON_MSK_AS_UTC = datetime(2026, 8, 6, 9, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _add_recording(db_session, user_id: str, created_at: datetime, status: str = "queued") -> Recording:
    recording = Recording(user_id=user_id, original_filename="f.mp4", s3_key_media="k", status=status)
    db_session.add(recording)
    db_session.commit()
    # created_at has a default, so overwrite it after insert to control the day
    recording.created_at = created_at
    db_session.commit()
    return recording


def test_uploads_today_counts_recordings_from_today(db_session):
    _add_recording(db_session, "u1", NOON_MSK_AS_UTC)
    _add_recording(db_session, "u1", NOON_MSK_AS_UTC + timedelta(hours=1))

    assert uploads_today(db_session, "u1", NOON_MSK_AS_UTC) == 2


def test_uploads_today_excludes_other_users(db_session):
    _add_recording(db_session, "u1", NOON_MSK_AS_UTC)
    _add_recording(db_session, "u2", NOON_MSK_AS_UTC)

    assert uploads_today(db_session, "u1", NOON_MSK_AS_UTC) == 1


def test_uploads_today_excludes_failed_recordings(db_session):
    _add_recording(db_session, "u1", NOON_MSK_AS_UTC, status="failed")
    _add_recording(db_session, "u1", NOON_MSK_AS_UTC, status="done")

    assert uploads_today(db_session, "u1", NOON_MSK_AS_UTC) == 1


def test_uploads_today_excludes_yesterdays_recordings(db_session):
    yesterday_late_msk = NOON_MSK_AS_UTC - timedelta(hours=13)  # 23:00 MSK the day before
    _add_recording(db_session, "u1", yesterday_late_msk)

    assert uploads_today(db_session, "u1", NOON_MSK_AS_UTC) == 0


def test_uploads_today_boundary_is_msk_midnight_not_utc_midnight(db_session):
    # 02:30 MSK on 08-06 is still "today" in Moscow, even though in UTC
    # that's 23:30 on 08-05 - i.e. still "yesterday" if you (wrongly) used
    # UTC midnight as the boundary instead of MSK midnight.
    early_morning_msk = datetime(2026, 8, 5, 23, 30, tzinfo=timezone.utc)
    _add_recording(db_session, "u1", early_morning_msk)

    assert uploads_today(db_session, "u1", NOON_MSK_AS_UTC) == 1


def test_next_reset_at_is_next_msk_midnight_in_utc():
    reset = next_reset_at(NOON_MSK_AS_UTC)

    reset_msk = reset.astimezone(timezone(timedelta(hours=3)))
    assert reset_msk.hour == 0
    assert reset_msk.minute == 0
    assert reset_msk.date() == (NOON_MSK_AS_UTC.astimezone(timezone(timedelta(hours=3))).date() + timedelta(days=1))
