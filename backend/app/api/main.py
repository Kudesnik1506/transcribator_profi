from contextlib import asynccontextmanager

from botocore.exceptions import ClientError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.api.routes_admin import router as admin_router
from app.api.routes_auth import router as auth_router
from app.api.routes_config import router as config_router
from app.api.routes_recordings import router as recordings_router
from app.api.routes_telegram import router as telegram_router
from app.api.routes_uploads import router as uploads_router
from app.auth import bootstrap_admin_user
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.search import apply_search_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    apply_search_schema(engine)

    db = SessionLocal()
    try:
        bootstrap_admin_user(db, settings.admin_email, settings.admin_password)
    finally:
        db.close()

    yield


app = FastAPI(title="Транскрибатор API", lifespan=lifespan)

# Браузер блокирует cross-origin fetch без этих заголовков — web/ и api/
# всегда работают на разных origin (разные порты минимум).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_base_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(config_router)
app.include_router(uploads_router)
app.include_router(recordings_router)
app.include_router(telegram_router)
app.include_router(admin_router)


@app.exception_handler(ClientError)
async def s3_client_error_handler(request: Request, exc: ClientError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": "хранилище S3 недоступно, попробуйте позже"})
