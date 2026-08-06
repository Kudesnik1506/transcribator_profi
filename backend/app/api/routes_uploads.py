import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_active_user
from app.config import settings
from app.s3 import (
    UploadedPart,
    abort_multipart_upload,
    complete_multipart_upload,
    create_multipart_upload,
    list_uploaded_parts,
    presign_upload_part_url,
)

router = APIRouter(dependencies=[Depends(get_active_user)])


class CreateMultipartUploadRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    size_bytes: int


class CreateMultipartUploadResponse(BaseModel):
    upload_id: str
    s3_key: str
    part_size: int
    part_count: int


@router.post("/uploads/multipart", response_model=CreateMultipartUploadResponse)
def create_multipart(payload: CreateMultipartUploadRequest) -> CreateMultipartUploadResponse:
    if payload.size_bytes <= 0:
        raise HTTPException(status_code=422, detail="некорректный размер файла")
    if payload.size_bytes > settings.max_upload_size_bytes:
        raise HTTPException(status_code=413, detail="файл больше допустимого размера")

    s3_key = f"media/{uuid.uuid4()}-{payload.filename}"
    upload_id = create_multipart_upload(s3_key, payload.content_type)
    part_size = settings.multipart_part_size_bytes
    part_count = -(-payload.size_bytes // part_size)

    return CreateMultipartUploadResponse(
        upload_id=upload_id, s3_key=s3_key, part_size=part_size, part_count=part_count
    )


class S3KeyRequest(BaseModel):
    """Base for requests that only need to identify the S3 object alongside upload_id in the path."""

    s3_key: str


class PartUrlResponse(BaseModel):
    upload_url: str


@router.post("/uploads/multipart/{upload_id}/parts/{part_number}", response_model=PartUrlResponse)
def get_part_upload_url(upload_id: str, part_number: int, payload: S3KeyRequest) -> PartUrlResponse:
    url = presign_upload_part_url(payload.s3_key, upload_id, part_number)
    return PartUrlResponse(upload_url=url)


class UploadedPartResponse(BaseModel):
    part_number: int
    etag: str
    size: int


@router.get("/uploads/multipart/{upload_id}/parts", response_model=list[UploadedPartResponse])
def get_uploaded_parts(upload_id: str, s3_key: str) -> list[UploadedPartResponse]:
    parts = list_uploaded_parts(s3_key, upload_id)
    return [UploadedPartResponse(part_number=p.part_number, etag=p.etag, size=p.size) for p in parts]


class CompletedPart(BaseModel):
    part_number: int
    etag: str


class CompleteMultipartRequest(S3KeyRequest):
    parts: list[CompletedPart]


@router.post("/uploads/multipart/{upload_id}/complete", status_code=204)
def complete_multipart(upload_id: str, payload: CompleteMultipartRequest) -> None:
    complete_multipart_upload(
        payload.s3_key,
        upload_id,
        [UploadedPart(part_number=p.part_number, etag=p.etag, size=0) for p in payload.parts],
    )


@router.post("/uploads/multipart/{upload_id}/abort", status_code=204)
def abort_multipart(upload_id: str, payload: S3KeyRequest) -> None:
    abort_multipart_upload(payload.s3_key, upload_id)
