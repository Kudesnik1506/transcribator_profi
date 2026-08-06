from contextlib import asynccontextmanager

from botocore.exceptions import ClientError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.api.routes_recordings import router as recordings_router
from app.api.routes_uploads import router as uploads_router
from app.db import Base, engine
from app.search import apply_search_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    apply_search_schema(engine)
    yield


app = FastAPI(title="Транскрибатор API", lifespan=lifespan)

app.include_router(uploads_router)
app.include_router(recordings_router)


@app.exception_handler(ClientError)
async def s3_client_error_handler(request: Request, exc: ClientError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": "хранилище S3 недоступно, попробуйте позже"})
