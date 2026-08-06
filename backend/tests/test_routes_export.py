import io

import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.api.main import app
from app.db import Base, get_db
from app.models import Recording, Segment


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


@pytest.fixture
def recording_with_segments(db_session, active_user):
    recording = Recording(user_id=active_user.id, original_filename="meeting.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()
    db_session.add(Segment(recording_id=recording.id, start_ms=0, end_ms=1500, text="Первый абзац"))
    db_session.add(Segment(recording_id=recording.id, start_ms=1500, end_ms=4000, text="Второй абзац"))
    db_session.commit()
    return recording


def test_export_txt_returns_plain_text(client, recording_with_segments, auth_headers):
    response = client.get(f"/recordings/{recording_with_segments.id}/export/txt", headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "meeting.txt" in response.headers["content-disposition"]
    assert response.text == "Первый абзац\nВторой абзац"


def test_export_srt_returns_subtitles_with_timecodes(client, recording_with_segments, auth_headers):
    response = client.get(f"/recordings/{recording_with_segments.id}/export/srt", headers=auth_headers)

    assert response.status_code == 200
    assert "meeting.srt" in response.headers["content-disposition"]
    assert "00:00:00,000 --> 00:00:01,500" in response.text
    assert "Первый абзац" in response.text


def test_export_docx_returns_valid_document(client, recording_with_segments, auth_headers):
    response = client.get(f"/recordings/{recording_with_segments.id}/export/docx", headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "meeting.docx" in response.headers["content-disposition"]

    doc = Document(io.BytesIO(response.content))
    texts = [p.text for p in doc.paragraphs if p.text]
    assert "Первый абзац" in texts
    assert "Второй абзац" in texts


def test_export_unknown_format_404(client, recording_with_segments, auth_headers):
    response = client.get(f"/recordings/{recording_with_segments.id}/export/pdf", headers=auth_headers)

    assert response.status_code == 404


def test_export_recording_missing_404(client, auth_headers):
    response = client.get("/recordings/does-not-exist/export/txt", headers=auth_headers)

    assert response.status_code == 404


def test_export_filename_with_quote_does_not_break_header(client, db_session, auth_headers, active_user):
    recording = Recording(
        user_id=active_user.id, original_filename='evil"name.mp4', s3_key_media="k", status="done"
    )
    db_session.add(recording)
    db_session.commit()
    db_session.add(Segment(recording_id=recording.id, start_ms=0, end_ms=1000, text="текст"))
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}/export/txt", headers=auth_headers)

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    ascii_part = disposition.split(";")[1]
    assert '"' not in ascii_part.split("=", 1)[1].strip()[1:-1]


def test_export_filename_with_slash_is_percent_encoded(client, db_session, auth_headers, active_user):
    recording = Recording(user_id=active_user.id, original_filename="a/b.mp4", s3_key_media="k", status="done")
    db_session.add(recording)
    db_session.commit()
    db_session.add(Segment(recording_id=recording.id, start_ms=0, end_ms=1000, text="текст"))
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}/export/txt", headers=auth_headers)

    disposition = response.headers["content-disposition"]
    utf8_part = disposition.split("filename*=UTF-8''")[1]
    assert "/" not in utf8_part


def test_export_filename_with_control_chars_is_sanitized(client, db_session, auth_headers, active_user):
    recording = Recording(
        user_id=active_user.id, original_filename="evil\r\nX-Injected: 1.mp4", s3_key_media="k", status="done"
    )
    db_session.add(recording)
    db_session.commit()
    db_session.add(Segment(recording_id=recording.id, start_ms=0, end_ms=1000, text="текст"))
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}/export/txt", headers=auth_headers)

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition
    assert "\n" not in disposition


def test_export_no_transcript_yet_409(client, db_session, auth_headers, active_user):
    recording = Recording(
        user_id=active_user.id, original_filename="meeting.mp4", s3_key_media="k", status="transcribing"
    )
    db_session.add(recording)
    db_session.commit()

    response = client.get(f"/recordings/{recording.id}/export/txt", headers=auth_headers)

    assert response.status_code == 409
