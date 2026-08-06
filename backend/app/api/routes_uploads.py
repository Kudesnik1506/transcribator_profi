import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.s3 import presign_put_url

router = APIRouter()


class PresignRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"


class PresignResponse(BaseModel):
    upload_url: str
    s3_key: str


@router.post("/uploads/presign", response_model=PresignResponse)
def create_presigned_upload(payload: PresignRequest) -> PresignResponse:
    s3_key = f"media/{uuid.uuid4()}-{payload.filename}"
    upload_url = presign_put_url(s3_key, payload.content_type)
    return PresignResponse(upload_url=upload_url, s3_key=s3_key)
