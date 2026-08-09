from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_active_user
from app.config import settings
from app.db import SessionLocal, get_db
from app.export import build_docx, build_srt, build_txt, content_disposition, export_filename
from app.models import Message, Recording, RecordingShare, Segment, User
from app.quota import enforce_daily_quota
from app.queue import get_queue
from app.s3 import presign_get_url
from app.search import search_segments
from app.worker.ai_gateway_client import stream_answer
from app.worker.dialog import TranscriptTooLongError, build_dialog_messages

router = APIRouter()

EXPORT_CONTENT_TYPES = {
    "txt": "text/plain; charset=utf-8",
    "srt": "application/x-subrip",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

EXPORT_BUILDERS = {
    "txt": lambda recording, segments: build_txt(segments).encode("utf-8"),
    "srt": lambda recording, segments: build_srt(segments).encode("utf-8"),
    "docx": lambda recording, segments: build_docx(recording.original_filename, segments),
}


def _get_owned_recording(db: Session, recording_id: str, user: User) -> Recording:
    # Admins can open any user's recording (e.g. from /admin/recordings or an
    # error log) — everyone else only their own.
    recording = db.get(Recording, recording_id)
    if recording is None or (recording.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="recording not found")
    return recording


def _get_accessible_recording(db: Session, recording_id: str, user: User) -> Recording:
    # Read-only access: owner, admin, or someone the owner shared it with.
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="recording not found")
    if recording.user_id == user.id or user.role == "admin":
        return recording
    shared = db.query(RecordingShare).filter_by(recording_id=recording.id, shared_with_user_id=user.id).first()
    if shared is None:
        raise HTTPException(status_code=404, detail="recording not found")
    return recording


class CreateRecordingRequest(BaseModel):
    s3_key: str
    original_filename: str
    content_type: str = "application/octet-stream"
    mode: Literal["fast", "deferred"] | None = None


class RecordingResponse(BaseModel):
    id: str
    status: str


class SegmentResponse(BaseModel):
    id: str
    start_ms: int
    end_ms: int
    text: str


class SummaryResponse(BaseModel):
    items: list[str]


class RecordingDetailResponse(BaseModel):
    id: str
    status: str
    mode: str
    progress_percent: int
    original_filename: str
    content_type: str
    media_url: str | None
    media_deleted_at: datetime | None
    error_message: str | None
    segments: list[SegmentResponse]
    summary: SummaryResponse | None
    is_owner: bool
    owner_email: str | None


class RecordingListItemResponse(BaseModel):
    id: str
    original_filename: str
    status: str
    mode: str
    progress_percent: int
    created_at: datetime
    owner_email: str | None = None


class ShareResponse(BaseModel):
    id: str
    email: str
    created_at: datetime


class CreateShareRequest(BaseModel):
    email: str


class MessageResponse(BaseModel):
    role: str
    content: str
    created_at: datetime


class AskQuestionRequest(BaseModel):
    content: str


class SearchMatchResponse(BaseModel):
    segment_id: str
    start_ms: int
    end_ms: int
    text: str


class SearchResponse(BaseModel):
    query: str
    total: int
    matches: list[SearchMatchResponse]


@router.get("/recordings", response_model=list[RecordingListItemResponse])
def list_recordings(
    db: Session = Depends(get_db), user: User = Depends(get_active_user)
) -> list[RecordingListItemResponse]:
    recordings = (
        db.query(Recording).filter_by(user_id=user.id).order_by(Recording.created_at.desc()).all()
    )
    return [
        RecordingListItemResponse(
            id=r.id,
            original_filename=r.original_filename,
            status=r.status,
            mode=r.mode,
            progress_percent=r.progress_percent,
            created_at=r.created_at,
        )
        for r in recordings
    ]


@router.get("/recordings/shared-with-me", response_model=list[RecordingListItemResponse])
def list_shared_recordings(
    db: Session = Depends(get_db), user: User = Depends(get_active_user)
) -> list[RecordingListItemResponse]:
    recordings = (
        db.query(Recording, User.email)
        .join(RecordingShare, RecordingShare.recording_id == Recording.id)
        .join(User, User.id == Recording.user_id)
        .filter(RecordingShare.shared_with_user_id == user.id)
        .order_by(Recording.created_at.desc())
        .all()
    )
    return [
        RecordingListItemResponse(
            id=r.id,
            original_filename=r.original_filename,
            status=r.status,
            mode=r.mode,
            progress_percent=r.progress_percent,
            created_at=r.created_at,
            owner_email=owner_email,
        )
        for r, owner_email in recordings
    ]


@router.post("/recordings", response_model=RecordingResponse, status_code=201)
async def create_recording(
    payload: CreateRecordingRequest,
    db: Session = Depends(get_db),
    queue=Depends(get_queue),
    user: User = Depends(get_active_user),
) -> RecordingResponse:
    enforce_daily_quota(db, user, datetime.now(timezone.utc))

    recording = Recording(
        user_id=user.id,
        original_filename=payload.original_filename,
        s3_key_media=payload.s3_key,
        content_type=payload.content_type,
        mode=payload.mode or settings.default_processing_mode,
        status="queued",
    )
    db.add(recording)
    db.commit()
    db.refresh(recording)

    await queue.enqueue_job("process_recording_job", recording.id)

    return RecordingResponse(id=recording.id, status=recording.status)


@router.get("/recordings/{recording_id}", response_model=RecordingDetailResponse)
def get_recording(
    recording_id: str, db: Session = Depends(get_db), user: User = Depends(get_active_user)
) -> RecordingDetailResponse:
    recording = _get_accessible_recording(db, recording_id, user)

    segments = sorted(recording.segments, key=lambda s: s.start_ms)
    owner = db.get(User, recording.user_id) if recording.user_id else None
    return RecordingDetailResponse(
        id=recording.id,
        status=recording.status,
        mode=recording.mode,
        progress_percent=recording.progress_percent,
        original_filename=recording.original_filename,
        content_type=recording.content_type,
        media_url=presign_get_url(recording.s3_key_media) if recording.media_deleted_at is None else None,
        media_deleted_at=recording.media_deleted_at,
        error_message=recording.error_message,
        segments=[SegmentResponse(id=s.id, start_ms=s.start_ms, end_ms=s.end_ms, text=s.text) for s in segments],
        summary=SummaryResponse(items=recording.summary.items) if recording.summary else None,
        is_owner=recording.user_id == user.id,
        owner_email=owner.email if owner else None,
    )


@router.get("/recordings/{recording_id}/search", response_model=SearchResponse)
def search_recording(
    recording_id: str, q: str, db: Session = Depends(get_db), user: User = Depends(get_active_user)
) -> SearchResponse:
    _get_accessible_recording(db, recording_id, user)

    if not q.strip():
        return SearchResponse(query=q, total=0, matches=[])

    matches = search_segments(db, recording_id, q)
    return SearchResponse(
        query=q,
        total=len(matches),
        matches=[
            SearchMatchResponse(segment_id=m.segment_id, start_ms=m.start_ms, end_ms=m.end_ms, text=m.text)
            for m in matches
        ],
    )


@router.get("/recordings/{recording_id}/export/{fmt}")
def export_recording(
    recording_id: str, fmt: str, db: Session = Depends(get_db), user: User = Depends(get_active_user)
) -> Response:
    if fmt not in EXPORT_CONTENT_TYPES:
        raise HTTPException(status_code=404, detail="unknown export format")

    recording = _get_accessible_recording(db, recording_id, user)

    segments = sorted(recording.segments, key=lambda s: s.start_ms)
    if not segments:
        raise HTTPException(status_code=409, detail="транскрипт ещё не готов")

    filename = export_filename(recording.original_filename, fmt)
    content = EXPORT_BUILDERS[fmt](recording, segments)

    return Response(
        content=content,
        media_type=EXPORT_CONTENT_TYPES[fmt],
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.post("/recordings/{recording_id}/retry", status_code=202)
async def retry_recording(
    recording_id: str,
    db: Session = Depends(get_db),
    queue=Depends(get_queue),
    user: User = Depends(get_active_user),
) -> RecordingResponse:
    recording = _get_owned_recording(db, recording_id, user)
    if recording.status != "partial":
        raise HTTPException(status_code=409, detail="повтор доступен только для частично обработанной записи")

    await queue.enqueue_job("retry_failed_chunks_job", recording.id)

    return RecordingResponse(id=recording.id, status=recording.status)


@router.get("/recordings/{recording_id}/messages", response_model=list[MessageResponse])
def list_messages(
    recording_id: str, db: Session = Depends(get_db), user: User = Depends(get_active_user)
) -> list[MessageResponse]:
    _get_accessible_recording(db, recording_id, user)

    messages = (
        db.query(Message).filter_by(recording_id=recording_id).order_by(Message.created_at).all()
    )
    return [MessageResponse(role=m.role, content=m.content, created_at=m.created_at) for m in messages]


@router.post("/recordings/{recording_id}/messages")
def ask_question(
    recording_id: str,
    payload: AskQuestionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_active_user),
) -> StreamingResponse:
    recording = _get_owned_recording(db, recording_id, user)

    segments = sorted(recording.segments, key=lambda s: s.start_ms)
    if recording.status not in ("done", "partial") or not segments:
        raise HTTPException(status_code=409, detail="транскрипт ещё не готов")

    transcript_text = "\n".join(s.text for s in segments)
    history_rows = (
        db.query(Message).filter_by(recording_id=recording_id).order_by(Message.created_at).all()
    )
    history = [{"role": m.role, "content": m.content} for m in history_rows]

    try:
        messages = build_dialog_messages(
            transcript_text, history, payload.content, settings.max_dialog_context_tokens
        )
    except TranscriptTooLongError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    db.add(Message(recording_id=recording_id, role="user", content=payload.content))
    db.commit()

    def stream_and_save_answer():
        answer_parts: list[str] = []
        try:
            for delta in stream_answer(messages):
                answer_parts.append(delta)
                yield delta
        except Exception:
            error_text = "Не удалось получить ответ — сервис ИИ временно недоступен."
            answer_parts.append(error_text)
            yield error_text

        answer_text = "".join(answer_parts)
        if answer_text:
            # A fresh session, not the request-scoped `db`: by the time this
            # generator finishes, FastAPI may already have torn down `db`'s
            # dependency lifecycle since streaming happens after the route
            # function returns its response object.
            save_db = SessionLocal()
            try:
                save_db.add(Message(recording_id=recording_id, role="assistant", content=answer_text))
                save_db.commit()
            finally:
                save_db.close()

    return StreamingResponse(stream_and_save_answer(), media_type="text/plain")


@router.post("/recordings/{recording_id}/shares", response_model=ShareResponse, status_code=201)
def create_share(
    recording_id: str,
    payload: CreateShareRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_active_user),
) -> ShareResponse:
    recording = _get_owned_recording(db, recording_id, user)

    recipient = db.query(User).filter_by(email=payload.email).first()
    if recipient is None:
        raise HTTPException(status_code=404, detail="пользователь не найден")
    if recipient.id == user.id:
        raise HTTPException(status_code=400, detail="нельзя поделиться записью с самим собой")

    share = (
        db.query(RecordingShare)
        .filter_by(recording_id=recording.id, shared_with_user_id=recipient.id)
        .first()
    )
    if share is None:
        share = RecordingShare(recording_id=recording.id, shared_with_user_id=recipient.id)
        db.add(share)
        db.commit()
        db.refresh(share)

    return ShareResponse(id=share.id, email=recipient.email, created_at=share.created_at)


@router.get("/recordings/{recording_id}/shares", response_model=list[ShareResponse])
def list_shares(
    recording_id: str, db: Session = Depends(get_db), user: User = Depends(get_active_user)
) -> list[ShareResponse]:
    recording = _get_owned_recording(db, recording_id, user)

    shares = (
        db.query(RecordingShare, User.email)
        .join(User, User.id == RecordingShare.shared_with_user_id)
        .filter(RecordingShare.recording_id == recording.id)
        .order_by(RecordingShare.created_at.desc())
        .all()
    )
    return [ShareResponse(id=share.id, email=email, created_at=share.created_at) for share, email in shares]


@router.delete("/recordings/{recording_id}/shares/{share_id}", status_code=204)
def revoke_share(
    recording_id: str, share_id: str, db: Session = Depends(get_db), user: User = Depends(get_active_user)
) -> None:
    recording = _get_owned_recording(db, recording_id, user)

    share = db.query(RecordingShare).filter_by(id=share_id, recording_id=recording.id).first()
    if share is None:
        raise HTTPException(status_code=404, detail="share not found")

    db.delete(share)
    db.commit()
