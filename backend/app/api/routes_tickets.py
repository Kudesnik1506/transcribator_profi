from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.activity_log import log_activity
from app.api.deps import get_active_user
from app.config import settings
from app.db import get_db
from app.models import Ticket, TicketEvent, TicketHypothesis, User
from app.s3 import presign_get_url, presign_put_url
from app.worker.notify import TelegramDeliveryError, send_telegram_text

router = APIRouter()


class ScreenshotUrlRequest(BaseModel):
    filename: str
    content_type: str
    size_bytes: int


class ScreenshotUrlResponse(BaseModel):
    upload_url: str
    s3_key: str


@router.post("/tickets/screenshot-url", response_model=ScreenshotUrlResponse)
def create_screenshot_url(
    payload: ScreenshotUrlRequest, user: User = Depends(get_active_user)
) -> ScreenshotUrlResponse:
    if not payload.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="скриншот должен быть изображением")
    if payload.size_bytes <= 0:
        raise HTTPException(status_code=422, detail="некорректный размер файла")
    if payload.size_bytes > settings.max_screenshot_size_bytes:
        raise HTTPException(status_code=413, detail="файл больше допустимого размера")

    s3_key = f"tickets/{uuid4()}-{payload.filename}"
    upload_url = presign_put_url(s3_key, payload.content_type)
    return ScreenshotUrlResponse(upload_url=upload_url, s3_key=s3_key)


class CreateTicketRequest(BaseModel):
    description: str
    page_url: str | None = None
    screenshot_s3_key: str | None = None


class TicketEventResponse(BaseModel):
    id: str
    status: str
    message: str
    author: str
    created_at: datetime


class TicketHypothesisResponse(BaseModel):
    id: str
    text: str
    verdict: str
    evidence: str | None
    created_at: datetime


class TicketListItemResponse(BaseModel):
    id: str
    number: int
    description: str
    status: str
    created_at: datetime


class TicketDetailResponse(BaseModel):
    id: str
    number: int
    description: str
    page_url: str | None
    screenshot_url: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    events: list[TicketEventResponse]
    hypotheses: list[TicketHypothesisResponse]


def _next_ticket_number(db: Session) -> int:
    current_max = db.query(func.max(Ticket.number)).scalar()
    return (current_max or 0) + 1


def _ticket_detail(ticket: Ticket) -> TicketDetailResponse:
    return TicketDetailResponse(
        id=ticket.id,
        number=ticket.number,
        description=ticket.description,
        page_url=ticket.page_url,
        screenshot_url=presign_get_url(ticket.screenshot_s3_key) if ticket.screenshot_s3_key else None,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        events=[
            TicketEventResponse(id=e.id, status=e.status, message=e.message, author=e.author, created_at=e.created_at)
            for e in ticket.events
        ],
        hypotheses=[
            TicketHypothesisResponse(id=h.id, text=h.text, verdict=h.verdict, evidence=h.evidence, created_at=h.created_at)
            for h in ticket.hypotheses
        ],
    )


def _alert_admin_of_new_ticket(ticket: Ticket, user: User) -> None:
    if not settings.admin_telegram_chat_id:
        return
    text = (
        f"Новый тикет #{ticket.number} от {user.email}\n"
        f"{ticket.description}\n"
        f"{settings.frontend_base_url}/admin/tickets/{ticket.id}"
    )
    try:
        send_telegram_text(settings.admin_telegram_chat_id, text)
    except TelegramDeliveryError:
        # Best-effort — the ticket itself is already saved; the admin can
        # still find it in /admin/tickets without the ping.
        pass


@router.post("/tickets", response_model=TicketDetailResponse, status_code=201)
def create_ticket(
    payload: CreateTicketRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_active_user),
) -> TicketDetailResponse:
    if not payload.description.strip():
        raise HTTPException(status_code=422, detail="опишите проблему")

    ticket = Ticket(
        number=_next_ticket_number(db),
        user_id=user.id,
        description=payload.description,
        page_url=payload.page_url,
        screenshot_s3_key=payload.screenshot_s3_key,
        status="new",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    db.add(TicketEvent(ticket_id=ticket.id, status="new", message="Заявка создана.", author="user"))
    db.commit()
    db.refresh(ticket)

    log_activity(db, user.id, "ticket_created", {"ticket_id": ticket.id, "number": ticket.number}, request)
    _alert_admin_of_new_ticket(ticket, user)

    return _ticket_detail(ticket)


@router.get("/tickets", response_model=list[TicketListItemResponse])
def list_my_tickets(db: Session = Depends(get_db), user: User = Depends(get_active_user)) -> list[TicketListItemResponse]:
    tickets = db.query(Ticket).filter_by(user_id=user.id).order_by(Ticket.created_at.desc()).all()
    return [
        TicketListItemResponse(id=t.id, number=t.number, description=t.description, status=t.status, created_at=t.created_at)
        for t in tickets
    ]


@router.get("/tickets/{ticket_id}", response_model=TicketDetailResponse)
def get_my_ticket(
    ticket_id: str, db: Session = Depends(get_db), user: User = Depends(get_active_user)
) -> TicketDetailResponse:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.user_id != user.id:
        raise HTTPException(status_code=404, detail="тикет не найден")
    return _ticket_detail(ticket)
