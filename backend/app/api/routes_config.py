from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter()


class PublicConfigResponse(BaseModel):
    default_processing_mode: str


@router.get("/config", response_model=PublicConfigResponse)
def get_public_config() -> PublicConfigResponse:
    return PublicConfigResponse(default_processing_mode=settings.default_processing_mode)
