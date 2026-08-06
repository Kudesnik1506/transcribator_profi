from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Recording
from app.queue import get_queue

router = APIRouter()


class CreateRecordingRequest(BaseModel):
    s3_key: str
    original_filename: str


class RecordingResponse(BaseModel):
    id: str
    status: str


class SegmentResponse(BaseModel):
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
    error_message: str | None
    segments: list[SegmentResponse]
    summary: SummaryResponse | None


@router.post("/recordings", response_model=RecordingResponse, status_code=201)
async def create_recording(
    payload: CreateRecordingRequest,
    db: Session = Depends(get_db),
    queue=Depends(get_queue),
) -> RecordingResponse:
    recording = Recording(
        original_filename=payload.original_filename,
        s3_key_media=payload.s3_key,
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
        error_message=recording.error_message,
        segments=[SegmentResponse(start_ms=s.start_ms, end_ms=s.end_ms, text=s.text) for s in segments],
        summary=SummaryResponse(items=recording.summary.items) if recording.summary else None,
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
