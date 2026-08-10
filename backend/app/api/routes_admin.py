from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.activity_log import log_activity
from app.api.deps import get_admin_user
from app.api.routes_auth import validate_password
from app.auth import hash_password
from app.db import get_db
from app.models import ActivityLog, ErrorLog, Recording, Ticket, TicketEvent, TicketHypothesis, User
from app.recording_deletion import purge_recording
from app.s3 import presign_get_url
from app.tickets import check_can_close

router = APIRouter(prefix="/admin", dependencies=[Depends(get_admin_user)])

# How far back to pull the reporting user's activity trail alongside a
# ticket — long enough to catch "what were they doing right before this
# broke", short enough not to dump their whole history.
TICKET_ACTIVITY_WINDOW = timedelta(hours=1)
# The ticket's own "ticket_created" activity row is written a moment after
# Ticket.created_at (separate log_activity() call, separate timestamp) —
# without this trailing slack it would fall just outside the window and
# vanish from its own ticket's activity trail.
TICKET_ACTIVITY_TRAILING_SLACK = timedelta(minutes=1)


class AdminUserResponse(BaseModel):
    id: str
    email: str
    role: str
    status: str
    created_at: datetime


def _user_response(user: User) -> AdminUserResponse:
    return AdminUserResponse(id=user.id, email=user.email, role=user.role, status=user.status, created_at=user.created_at)


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(db: Session = Depends(get_db)) -> list[AdminUserResponse]:
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [_user_response(u) for u in users]


def _get_user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="пользователь не найден")
    return user


@router.post("/users/{user_id}/approve", response_model=AdminUserResponse)
def approve_user(
    user_id: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)
) -> AdminUserResponse:
    user = _get_user_or_404(db, user_id)
    user.status = "active"
    db.commit()
    log_activity(db, admin.id, "user_approved", {"target_user_id": user_id}, request)
    return _user_response(user)


@router.post("/users/{user_id}/block", response_model=AdminUserResponse)
def block_user(
    user_id: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)
) -> AdminUserResponse:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="нельзя заблокировать самого себя")
    user = _get_user_or_404(db, user_id)
    user.status = "blocked"
    db.commit()
    log_activity(db, admin.id, "user_blocked", {"target_user_id": user_id}, request)
    return _user_response(user)


class AdminResetPasswordRequest(BaseModel):
    new_password: str


@router.post("/users/{user_id}/reset-password", status_code=204)
def reset_user_password(
    user_id: str,
    payload: AdminResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> None:
    user = _get_user_or_404(db, user_id)
    validate_password(payload.new_password)

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    log_activity(db, admin.id, "admin_reset_password", {"target_user_id": user_id}, request)


class AdminRecordingResponse(BaseModel):
    id: str
    original_filename: str
    status: str
    mode: str
    progress_percent: int
    user_id: str | None
    user_email: str | None
    created_at: datetime


@router.get("/recordings", response_model=list[AdminRecordingResponse])
def list_all_recordings(
    user_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list[AdminRecordingResponse]:
    query = db.query(Recording).order_by(Recording.created_at.desc())
    if user_id:
        query = query.filter(Recording.user_id == user_id)
    if status:
        query = query.filter(Recording.status == status)

    recordings = query.all()
    users_by_id = {u.id: u for u in db.query(User).all()}

    return [
        AdminRecordingResponse(
            id=r.id,
            original_filename=r.original_filename,
            status=r.status,
            mode=r.mode,
            progress_percent=r.progress_percent,
            user_id=r.user_id,
            user_email=users_by_id[r.user_id].email if r.user_id in users_by_id else None,
            created_at=r.created_at,
        )
        for r in recordings
    ]


@router.delete("/recordings/{recording_id}", status_code=204)
def delete_recording(
    recording_id: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)
) -> None:
    recording = db.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="запись не найдена")

    purge_recording(db, recording)
    log_activity(db, admin.id, "recording_deleted_by_admin", {"recording_id": recording_id}, request)


class AdminErrorLogResponse(BaseModel):
    id: str
    recording_id: str | None
    level: str
    message: str
    context: dict
    created_at: datetime


@router.get("/error-logs", response_model=list[AdminErrorLogResponse])
def list_error_logs(
    level: str | None = None,
    recording_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[AdminErrorLogResponse]:
    query = db.query(ErrorLog).order_by(ErrorLog.created_at.desc())
    if level:
        query = query.filter(ErrorLog.level == level)
    if recording_id:
        query = query.filter(ErrorLog.recording_id.startswith(recording_id))

    logs = query.all()
    return [
        AdminErrorLogResponse(
            id=log.id,
            recording_id=log.recording_id,
            level=log.level,
            message=log.message,
            context=log.context,
            created_at=log.created_at,
        )
        for log in logs
    ]


class AdminActivityLogResponse(BaseModel):
    id: str
    user_id: str | None
    user_email: str | None
    action: str
    context: dict
    ip: str | None
    user_agent: str | None
    created_at: datetime


@router.get("/activity", response_model=list[AdminActivityLogResponse])
def list_activity_logs(
    user_id: str | None = None,
    action: str | None = None,
    db: Session = Depends(get_db),
) -> list[AdminActivityLogResponse]:
    query = db.query(ActivityLog).order_by(ActivityLog.created_at.desc())
    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)
    if action:
        query = query.filter(ActivityLog.action == action)

    logs = query.all()
    users_by_id = {u.id: u for u in db.query(User).all()}
    return [
        AdminActivityLogResponse(
            id=log.id,
            user_id=log.user_id,
            user_email=users_by_id[log.user_id].email if log.user_id in users_by_id else None,
            action=log.action,
            context=log.context,
            ip=log.ip,
            user_agent=log.user_agent,
            created_at=log.created_at,
        )
        for log in logs
    ]


# --- tickets ---


def _get_ticket_or_404(db: Session, ticket_id: str) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="тикет не найден")
    return ticket


class AdminTicketListItemResponse(BaseModel):
    id: str
    number: int
    user_email: str
    description: str
    status: str
    created_at: datetime


@router.get("/tickets", response_model=list[AdminTicketListItemResponse])
def list_tickets(status: str | None = None, db: Session = Depends(get_db)) -> list[AdminTicketListItemResponse]:
    query = db.query(Ticket).order_by(Ticket.created_at.desc())
    if status:
        query = query.filter(Ticket.status == status)

    tickets = query.all()
    users_by_id = {u.id: u for u in db.query(User).all()}
    return [
        AdminTicketListItemResponse(
            id=t.id,
            number=t.number,
            user_email=users_by_id[t.user_id].email if t.user_id in users_by_id else "неизвестно",
            description=t.description,
            status=t.status,
            created_at=t.created_at,
        )
        for t in tickets
    ]


class AdminTicketEventResponse(BaseModel):
    id: str
    status: str
    message: str
    author: str
    created_at: datetime


class AdminTicketHypothesisResponse(BaseModel):
    id: str
    text: str
    verdict: str
    evidence: str | None
    created_at: datetime


class ActivitySnapshotResponse(BaseModel):
    action: str
    context: dict
    created_at: datetime


class AdminTicketDetailResponse(BaseModel):
    id: str
    number: int
    user_email: str
    description: str
    page_url: str | None
    screenshot_url: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    events: list[AdminTicketEventResponse]
    hypotheses: list[AdminTicketHypothesisResponse]
    recent_activity: list[ActivitySnapshotResponse]


def _ticket_detail_response(db: Session, ticket: Ticket) -> AdminTicketDetailResponse:
    author = db.get(User, ticket.user_id)
    window_start = ticket.created_at - TICKET_ACTIVITY_WINDOW
    window_end = ticket.created_at + TICKET_ACTIVITY_TRAILING_SLACK
    recent_activity = (
        db.query(ActivityLog)
        .filter(
            ActivityLog.user_id == ticket.user_id,
            ActivityLog.created_at >= window_start,
            ActivityLog.created_at <= window_end,
        )
        .order_by(ActivityLog.created_at.desc())
        .all()
    )
    return AdminTicketDetailResponse(
        id=ticket.id,
        number=ticket.number,
        user_email=author.email if author else "неизвестно",
        description=ticket.description,
        page_url=ticket.page_url,
        screenshot_url=presign_get_url(ticket.screenshot_s3_key) if ticket.screenshot_s3_key else None,
        status=ticket.status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        events=[
            AdminTicketEventResponse(id=e.id, status=e.status, message=e.message, author=e.author, created_at=e.created_at)
            for e in ticket.events
        ],
        hypotheses=[
            AdminTicketHypothesisResponse(id=h.id, text=h.text, verdict=h.verdict, evidence=h.evidence, created_at=h.created_at)
            for h in ticket.hypotheses
        ],
        recent_activity=[
            ActivitySnapshotResponse(action=a.action, context=a.context, created_at=a.created_at)
            for a in recent_activity
        ],
    )


@router.get("/tickets/{ticket_id}", response_model=AdminTicketDetailResponse)
def get_ticket(ticket_id: str, db: Session = Depends(get_db)) -> AdminTicketDetailResponse:
    ticket = _get_ticket_or_404(db, ticket_id)
    return _ticket_detail_response(db, ticket)


class CreateHypothesisRequest(BaseModel):
    text: str


@router.post("/tickets/{ticket_id}/hypotheses", response_model=AdminTicketDetailResponse, status_code=201)
def create_hypothesis(
    ticket_id: str, payload: CreateHypothesisRequest, db: Session = Depends(get_db)
) -> AdminTicketDetailResponse:
    ticket = _get_ticket_or_404(db, ticket_id)
    if not payload.text.strip():
        raise HTTPException(status_code=422, detail="сформулируйте гипотезу")

    db.add(TicketHypothesis(ticket_id=ticket.id, text=payload.text, verdict="pending"))
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ticket)
    return _ticket_detail_response(db, ticket)


class UpdateHypothesisRequest(BaseModel):
    verdict: str
    evidence: str | None = None


VALID_VERDICTS = {"pending", "rejected", "confirmed"}


@router.patch("/tickets/{ticket_id}/hypotheses/{hypothesis_id}", response_model=AdminTicketDetailResponse)
def update_hypothesis(
    ticket_id: str, hypothesis_id: str, payload: UpdateHypothesisRequest, db: Session = Depends(get_db)
) -> AdminTicketDetailResponse:
    ticket = _get_ticket_or_404(db, ticket_id)
    if payload.verdict not in VALID_VERDICTS:
        raise HTTPException(status_code=422, detail=f"verdict должен быть одним из {sorted(VALID_VERDICTS)}")

    hypothesis = db.get(TicketHypothesis, hypothesis_id)
    if hypothesis is None or hypothesis.ticket_id != ticket.id:
        raise HTTPException(status_code=404, detail="гипотеза не найдена")
    if payload.verdict == "rejected" and not (payload.evidence and payload.evidence.strip()):
        raise HTTPException(status_code=422, detail="для rejected нужно заполнить evidence — чем проверяли и что показало")

    hypothesis.verdict = payload.verdict
    hypothesis.evidence = payload.evidence
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ticket)
    return _ticket_detail_response(db, ticket)


VALID_TICKET_STATUSES = {"new", "investigating", "fix_ready", "deployed", "rejected", "need_info"}


class CreateTicketEventRequest(BaseModel):
    status: str
    message: str


@router.post("/tickets/{ticket_id}/events", response_model=AdminTicketDetailResponse, status_code=201)
def create_ticket_event(
    ticket_id: str,
    payload: CreateTicketEventRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
) -> AdminTicketDetailResponse:
    ticket = _get_ticket_or_404(db, ticket_id)
    if payload.status not in VALID_TICKET_STATUSES:
        raise HTTPException(status_code=422, detail=f"status должен быть одним из {sorted(VALID_TICKET_STATUSES)}")
    if not payload.message.strip():
        raise HTTPException(status_code=422, detail="опишите, что произошло на этом этапе")

    # The gate the user asked for, in code: no hypothesis pool, no fix_ready.
    if payload.status == "fix_ready":
        reason = check_can_close(ticket.hypotheses)
        if reason is not None:
            raise HTTPException(status_code=409, detail=reason)

    # Diagnosis can't be skipped — deployed only follows a fix that's
    # already been declared ready.
    if payload.status == "deployed" and ticket.status != "fix_ready":
        raise HTTPException(status_code=409, detail="в deployed можно перейти только из fix_ready")

    db.add(TicketEvent(ticket_id=ticket.id, status=payload.status, message=payload.message, author="agent"))
    ticket.status = payload.status
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ticket)

    log_activity(
        db, admin.id, "ticket_status_changed", {"ticket_id": ticket.id, "status": payload.status}, request
    )

    return _ticket_detail_response(db, ticket)
