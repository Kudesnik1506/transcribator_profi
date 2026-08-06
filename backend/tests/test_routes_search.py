import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.routes_recordings as routes_recordings
import app.models  # noqa: F401 - registers tables on Base.metadata
from app.api.main import app
from app.db import Base, get_db
from app.models import Recording
from app.search import SearchMatch


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
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_search_recording_returns_matches(client, db_session, monkeypatch, auth_headers, active_user):
    recording = Recording(user_id=active_user.id, original_filename="m.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()

    monkeypatch.setattr(
        routes_recordings,
        "search_segments",
        lambda db, rid, q: [SearchMatch(segment_id="s1", start_ms=1000, end_ms=2000, text="говорили про бюджет")],
    )

    response = client.get(f"/recordings/{recording.id}/search", params={"q": "бюджет"}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["query"] == "бюджет"
    assert body["matches"][0] == {
        "segment_id": "s1",
        "start_ms": 1000,
        "end_ms": 2000,
        "text": "говорили про бюджет",
    }


def test_search_recording_404_when_missing(client, auth_headers):
    response = client.get("/recordings/does-not-exist/search", params={"q": "x"}, headers=auth_headers)

    assert response.status_code == 404


def test_search_recording_empty_query_returns_no_matches(client, db_session, monkeypatch, auth_headers, active_user):
    recording = Recording(user_id=active_user.id, original_filename="m.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()

    def must_not_be_called(db, rid, q):
        raise AssertionError("search_segments should not be called for a blank query")

    monkeypatch.setattr(routes_recordings, "search_segments", must_not_be_called)

    response = client.get(f"/recordings/{recording.id}/search", params={"q": "   "}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_search_recording_requires_q_param(client, db_session, auth_headers, active_user):
    recording = Recording(user_id=active_user.id, original_filename="m.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}/search", headers=auth_headers)

    assert response.status_code == 422
