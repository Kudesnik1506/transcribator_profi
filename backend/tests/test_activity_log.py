from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.activity_log import log_activity
from app.db import Base
from app.models import ActivityLog, User
from app.retention import purge_expired_activity_logs

NOW = datetime(2026, 8, 6, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def user(db_session):
    u = User(email="user@example.com", password_hash="x", role="user", status="active")
    db_session.add(u)
    db_session.commit()
    return u


def test_log_activity_writes_row_with_context(db_session, user):
    log_activity(db_session, user.id, "login", {"foo": "bar"})

    row = db_session.query(ActivityLog).one()
    assert row.user_id == user.id
    assert row.action == "login"
    assert row.context == {"foo": "bar"}
    assert row.created_at is not None


def test_log_activity_defaults_context_to_empty_dict(db_session, user):
    log_activity(db_session, user.id, "logout")

    row = db_session.query(ActivityLog).one()
    assert row.context == {}


def test_log_activity_allows_null_user_id(db_session):
    log_activity(db_session, None, "anonymous_event")

    row = db_session.query(ActivityLog).one()
    assert row.user_id is None


def _make_log(db_session, created_at, action="login") -> ActivityLog:
    log = ActivityLog(user_id=None, action=action, context={})
    db_session.add(log)
    db_session.commit()
    log.created_at = created_at
    db_session.commit()
    return log


def test_purge_expired_activity_logs_removes_old_rows(db_session):
    _make_log(db_session, NOW - timedelta(days=200))

    count = purge_expired_activity_logs(db_session, NOW, retention_days=90)

    assert count == 1
    assert db_session.query(ActivityLog).count() == 0


def test_purge_expired_activity_logs_keeps_recent_rows(db_session):
    recent = _make_log(db_session, NOW - timedelta(days=1))

    count = purge_expired_activity_logs(db_session, NOW, retention_days=90)

    assert count == 0
    assert db_session.get(ActivityLog, recent.id) is not None
