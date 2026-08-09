import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="user")
    status: Mapped[str] = mapped_column(String, default="pending")
    telegram_chat_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String)
    s3_key_media: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String, default="application/octet-stream")
    mode: Mapped[str] = mapped_column(String, default="deferred")
    status: Mapped[str] = mapped_column(String, default="queued")
    progress_percent: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    notified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Guards against duplicate notifications for the same outcome (e.g. a
    # re-entrant _finalize call) without blocking a genuinely new outcome —
    # a retry can move partial -> done, and that deserves its own email.
    notified_status: Mapped[str | None] = mapped_column(String, nullable=True)
    media_deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="recording", cascade="all, delete-orphan")
    segments: Mapped[list["Segment"]] = relationship(back_populates="recording", cascade="all, delete-orphan")
    summary: Mapped["Summary"] = relationship(back_populates="recording", cascade="all, delete-orphan", uselist=False)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    recording_id: Mapped[str] = mapped_column(ForeignKey("recordings.id"))
    idx: Mapped[int] = mapped_column()
    start_sec: Mapped[float] = mapped_column()
    end_sec: Mapped[float] = mapped_column()
    status: Mapped[str] = mapped_column(String, default="pending")
    attempts: Mapped[int] = mapped_column(default=0)

    recording: Mapped["Recording"] = relationship(back_populates="chunks")


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    recording_id: Mapped[str] = mapped_column(ForeignKey("recordings.id"))
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("chunks.id"), nullable=True)
    start_ms: Mapped[int] = mapped_column()
    end_ms: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    speaker: Mapped[str | None] = mapped_column(String, nullable=True)

    recording: Mapped["Recording"] = relationship(back_populates="segments")


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    recording_id: Mapped[str | None] = mapped_column(ForeignKey("recordings.id"), nullable=True)
    level: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    recording_id: Mapped[str] = mapped_column(ForeignKey("recordings.id"))
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class TelegramLinkCode(Base):
    __tablename__ = "telegram_link_codes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    expires_at: Mapped[datetime] = mapped_column()


class RecordingShare(Base):
    __tablename__ = "recording_shares"
    __table_args__ = (UniqueConstraint("recording_id", "shared_with_user_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    recording_id: Mapped[str] = mapped_column(ForeignKey("recordings.id"))
    shared_with_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    can_ask: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    number: Mapped[int] = mapped_column(unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    description: Mapped[str] = mapped_column(Text)
    page_url: Mapped[str | None] = mapped_column(String, nullable=True)
    screenshot_s3_key: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="new")
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now)

    events: Mapped[list["TicketEvent"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketEvent.created_at"
    )
    hypotheses: Mapped[list["TicketHypothesis"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketHypothesis.created_at"
    )


class TicketEvent(Base):
    __tablename__ = "ticket_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"))
    status: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    ticket: Mapped["Ticket"] = relationship(back_populates="events")


class TicketHypothesis(Base):
    __tablename__ = "ticket_hypotheses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"))
    text: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String, default="pending")
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    ticket: Mapped["Ticket"] = relationship(back_populates="hypotheses")


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    recording_id: Mapped[str] = mapped_column(ForeignKey("recordings.id"))
    items: Mapped[list] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    recording: Mapped["Recording"] = relationship(back_populates="summary")
