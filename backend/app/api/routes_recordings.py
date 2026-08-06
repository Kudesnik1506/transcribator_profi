from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_db
from app.models import Message, Recording, Segment
from app.queue import get_queue
from app.s3 import presign_get_url
from app.search import search_segments
from app.worker.ai_gateway_client import stream_answer
from app.worker.dialog import TranscriptTooLongError, build_dialog_messages

router = APIRouter()


class CreateRecordingRequest(BaseModel):
    s3_key: str
    original_filename: str
    content_type: str = "application/octet-stream"


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
    progress_percent: int
    original_filename: str
    content_type: str
    media_url: str
    error_message: str | None
    segments: list[SegmentResponse]
    summary: SummaryResponse | None


class RecordingListItemResponse(BaseModel):
    id: str
    original_filename: str
    status: str
    progress_percent: int
    created_at: datetime


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
def list_recordings(db: Session = Depends(get_db)) -> list[RecordingListItemResponse]:
    recordings = db.query(Recording).order_by(Recording.created_at.desc()).all()
    return [
        RecordingListItemResponse(
            id=r.id,
            original_filename=r.original_filename,
            status=r.status,
            progress_percent=r.progress_percent,
            created_at=r.created_at,
        )
        for r in recordings
    ]


@router.post("/recordings", response_model=RecordingResponse, status_code=201)
async def create_recording(
    payload: CreateRecordingRequest,
    db: Session = Depends(get_db),
    queue=Depends(get_queue),
) -> RecordingResponse:
    recording = Recording(
        original_filename=payload.original_filename,
        s3_key_media=payload.s3_key,
        content_type=payload.content_type,
        status="queued",
    )
    db.add(recording)
    db.commit()
    db.refresh(recording)

    await queue.enqueue_job("process_recording_job", recording.id)

    return RecordingResponse(id=recording.id, status=recording.status)


@router.get("/recordings/{recording_id}", response_model=RecordingDetailResponse)
def get_recording(recording_id: str, db: Session = Depends(get_db)) -> RecordingDetailResponse:
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="recording not found")

    segments = sorted(recording.segments, key=lambda s: s.start_ms)
    return RecordingDetailResponse(
        id=recording.id,
        status=recording.status,
        progress_percent=recording.progress_percent,
        original_filename=recording.original_filename,
        content_type=recording.content_type,
        media_url=presign_get_url(recording.s3_key_media),
        error_message=recording.error_message,
        segments=[SegmentResponse(id=s.id, start_ms=s.start_ms, end_ms=s.end_ms, text=s.text) for s in segments],
        summary=SummaryResponse(items=recording.summary.items) if recording.summary else None,
    )


@router.get("/recordings/{recording_id}/search", response_model=SearchResponse)
def search_recording(recording_id: str, q: str, db: Session = Depends(get_db)) -> SearchResponse:
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="recording not found")

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


@router.post("/recordings/{recording_id}/retry", status_code=202)
async def retry_recording(
    recording_id: str,
    db: Session = Depends(get_db),
    queue=Depends(get_queue),
) -> RecordingResponse:
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="recording not found")

    await queue.enqueue_job("retry_failed_chunks_job", recording.id)

    return RecordingResponse(id=recording.id, status=recording.status)


@router.get("/recordings/{recording_id}/messages", response_model=list[MessageResponse])
def list_messages(recording_id: str, db: Session = Depends(get_db)) -> list[MessageResponse]:
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="recording not found")

    messages = (
        db.query(Message).filter_by(recording_id=recording_id).order_by(Message.created_at).all()
    )
    return [MessageResponse(role=m.role, content=m.content, created_at=m.created_at) for m in messages]


@router.post("/recordings/{recording_id}/messages")
def ask_question(
    recording_id: str, payload: AskQuestionRequest, db: Session = Depends(get_db)
) -> StreamingResponse:
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="recording not found")

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
