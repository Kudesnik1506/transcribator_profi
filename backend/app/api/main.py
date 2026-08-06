from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.api.routes_recordings import router as recordings_router
from app.api.routes_uploads import router as uploads_router
from app.db import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Транскрибатор API", lifespan=lifespan)

app.include_router(uploads_router)
app.include_router(recordings_router)
