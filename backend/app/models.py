import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    original_filename: Mapped[str] = mapped_column(String)
    s3_key_media: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    segments: Mapped[list["Segment"]] = relationship(back_populates="recording", cascade="all, delete-orphan")
    summary: Mapped["Summary"] = relationship(back_populates="recording", cascade="all, delete-orphan", uselist=False)


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    recording_id: Mapped[str] = mapped_column(ForeignKey("recordings.id"))
    start_ms: Mapped[int] = mapped_column()
    end_ms: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    speaker: Mapped[str | None] = mapped_column(String, nullable=True)

    recording: Mapped["Recording"] = relationship(back_populates="segments")


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    recording_id: Mapped[str] = mapped_column(ForeignKey("recordings.id"))
    items: Mapped[list] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    recording: Mapped["Recording"] = relationship(back_populates="summary")
