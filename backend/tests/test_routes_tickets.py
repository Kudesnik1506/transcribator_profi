import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.api import routes_tickets
from app.api.main import app
from app.db import Base, get_db
from app.models import ActivityLog, Ticket, TicketHypothesis, User


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _create_ticket(client, headers, description="всё сломалось"):
    return client.post("/tickets", json={"description": description}, headers=headers)


# --- screenshot presign ---


def test_create_screenshot_url_rejects_non_image(client, auth_headers):
    response = client.post(
        "/tickets/screenshot-url",
        json={"filename": "f.txt", "content_type": "text/plain", "size_bytes": 100},
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_create_screenshot_url_rejects_oversized(client, auth_headers):
    response = client.post(
        "/tickets/screenshot-url",
        json={"filename": "f.png", "content_type": "image/png", "size_bytes": 999_999_999},
        headers=auth_headers,
    )

    assert response.status_code == 413


def test_create_screenshot_url_returns_upload_url_and_key(client, auth_headers):
    response = client.post(
        "/tickets/screenshot-url",
        json={"filename": "screenshot.png", "content_type": "image/png", "size_bytes": 12345},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["upload_url"].startswith("http")
    assert body["s3_key"].startswith("tickets/")
    assert body["s3_key"].endswith("screenshot.png")


def test_create_screenshot_url_requires_auth(client):
    response = client.post(
        "/tickets/screenshot-url", json={"filename": "f.png", "content_type": "image/png", "size_bytes": 100}
    )

    assert response.status_code == 401


# --- create ticket ---


def test_create_ticket_creates_ticket_and_first_event(client, db_session, auth_headers, active_user):
    response = _create_ticket(client, auth_headers, description="кнопка не работает")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "new"
    assert body["number"] == 1
    assert len(body["events"]) == 1
    assert body["events"][0]["status"] == "new"
    assert body["events"][0]["author"] == "user"

    ticket = db_session.query(Ticket).one()
    assert ticket.user_id == active_user.id


def test_create_ticket_rejects_empty_description(client, auth_headers):
    response = client.post("/tickets", json={"description": "   "}, headers=auth_headers)

    assert response.status_code == 422


def test_create_ticket_leaves_activity_log(client, db_session, auth_headers, active_user):
    response = _create_ticket(client, auth_headers)

    ticket_id = response.json()["id"]
    log = db_session.query(ActivityLog).filter_by(user_id=active_user.id, action="ticket_created").first()
    assert log is not None
    assert log.context["ticket_id"] == ticket_id


def test_ticket_numbers_increment(client, auth_headers):
    first = _create_ticket(client, auth_headers, description="первая").json()
    second = _create_ticket(client, auth_headers, description="вторая").json()

    assert second["number"] == first["number"] + 1


def test_create_ticket_pings_telegram_when_configured(client, auth_headers, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "admin_telegram_chat_id", "12345")
    calls = []
    monkeypatch.setattr(routes_tickets, "send_telegram_text", lambda chat_id, text: calls.append((chat_id, text)))

    response = _create_ticket(client, auth_headers)

    assert response.status_code == 201
    assert len(calls) == 1
    assert calls[0][0] == "12345"


def test_create_ticket_survives_telegram_failure(client, auth_headers, monkeypatch):
    from app.config import settings
    from app.worker.notify import TelegramDeliveryError

    monkeypatch.setattr(settings, "admin_telegram_chat_id", "12345")

    def boom(chat_id, text):
        raise TelegramDeliveryError("bot down")

    monkeypatch.setattr(routes_tickets, "send_telegram_text", boom)

    response = _create_ticket(client, auth_headers)

    assert response.status_code == 201


# --- list/get own tickets ---


def test_list_my_tickets_only_shows_own(client, db_session, auth_headers):
    other = User(email="other@example.com", password_hash="x", role="user", status="active")
    db_session.add(other)
    db_session.commit()
    db_session.add(Ticket(number=1, user_id=other.id, description="чужой", status="new"))
    db_session.commit()

    _create_ticket(client, auth_headers, description="мой")

    response = client.get("/tickets", headers=auth_headers)

    assert response.status_code == 200
    assert [t["description"] for t in response.json()] == ["мой"]


def test_get_ticket_404_for_other_users_ticket(client, db_session, auth_headers):
    other = User(email="other@example.com", password_hash="x", role="user", status="active")
    db_session.add(other)
    db_session.commit()
    ticket = Ticket(number=1, user_id=other.id, description="чужой", status="new")
    db_session.add(ticket)
    db_session.commit()

    response = client.get(f"/tickets/{ticket.id}", headers=auth_headers)

    assert response.status_code == 404


def test_get_own_ticket_succeeds(client, auth_headers):
    ticket_id = _create_ticket(client, auth_headers).json()["id"]

    response = client.get(f"/tickets/{ticket_id}", headers=auth_headers)

    assert response.status_code == 200


# --- admin access control ---


def test_admin_ticket_routes_reject_regular_user(client, auth_headers):
    assert client.get("/admin/tickets", headers=auth_headers).status_code == 403


def test_admin_ticket_routes_reject_missing_auth(client):
    assert client.get("/admin/tickets").status_code == 401


# --- admin: list/detail ---


def test_admin_list_tickets_shows_all(client, admin_auth_headers, auth_headers):
    _create_ticket(client, auth_headers, description="от пользователя")

    response = client.get("/admin/tickets", headers=admin_auth_headers)

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["user_email"] == "user@example.com"


def test_admin_list_tickets_filters_by_status(client, admin_auth_headers, auth_headers):
    _create_ticket(client, auth_headers)

    response = client.get("/admin/tickets?status=investigating", headers=admin_auth_headers)

    assert response.json() == []


def test_admin_get_ticket_includes_recent_activity(client, admin_auth_headers, auth_headers):
    ticket_id = _create_ticket(client, auth_headers).json()["id"]

    response = client.get(f"/admin/tickets/{ticket_id}", headers=admin_auth_headers)

    assert response.status_code == 200
    actions = [a["action"] for a in response.json()["recent_activity"]]
    assert "ticket_created" in actions


def test_admin_get_ticket_404_when_missing(client, admin_auth_headers):
    response = client.get("/admin/tickets/does-not-exist", headers=admin_auth_headers)

    assert response.status_code == 404


# --- admin: hypotheses ---


def test_create_hypothesis(client, admin_auth_headers, auth_headers):
    ticket_id = _create_ticket(client, auth_headers).json()["id"]

    response = client.post(
        f"/admin/tickets/{ticket_id}/hypotheses", json={"text": "может, дело в CORS"}, headers=admin_auth_headers
    )

    assert response.status_code == 201
    assert len(response.json()["hypotheses"]) == 1
    assert response.json()["hypotheses"][0]["verdict"] == "pending"


def test_create_hypothesis_rejects_blank_text(client, admin_auth_headers, auth_headers):
    ticket_id = _create_ticket(client, auth_headers).json()["id"]

    response = client.post(f"/admin/tickets/{ticket_id}/hypotheses", json={"text": "  "}, headers=admin_auth_headers)

    assert response.status_code == 422


def test_update_hypothesis_confirmed(client, db_session, admin_auth_headers, auth_headers):
    ticket_id = _create_ticket(client, auth_headers).json()["id"]
    hyp_id = client.post(
        f"/admin/tickets/{ticket_id}/hypotheses", json={"text": "гипотеза"}, headers=admin_auth_headers
    ).json()["hypotheses"][0]["id"]

    response = client.patch(
        f"/admin/tickets/{ticket_id}/hypotheses/{hyp_id}",
        json={"verdict": "confirmed", "evidence": "воспроизвёл локально"},
        headers=admin_auth_headers,
    )

    assert response.status_code == 200
    hyp = db_session.get(TicketHypothesis, hyp_id)
    assert hyp.verdict == "confirmed"
    assert hyp.evidence == "воспроизвёл локально"


def test_update_hypothesis_rejected_requires_evidence(client, admin_auth_headers, auth_headers):
    ticket_id = _create_ticket(client, auth_headers).json()["id"]
    hyp_id = client.post(
        f"/admin/tickets/{ticket_id}/hypotheses", json={"text": "гипотеза"}, headers=admin_auth_headers
    ).json()["hypotheses"][0]["id"]

    response = client.patch(
        f"/admin/tickets/{ticket_id}/hypotheses/{hyp_id}", json={"verdict": "rejected"}, headers=admin_auth_headers
    )

    assert response.status_code == 422


def test_update_hypothesis_rejects_invalid_verdict(client, admin_auth_headers, auth_headers):
    ticket_id = _create_ticket(client, auth_headers).json()["id"]
    hyp_id = client.post(
        f"/admin/tickets/{ticket_id}/hypotheses", json={"text": "гипотеза"}, headers=admin_auth_headers
    ).json()["hypotheses"][0]["id"]

    response = client.patch(
        f"/admin/tickets/{ticket_id}/hypotheses/{hyp_id}", json={"verdict": "maybe"}, headers=admin_auth_headers
    )

    assert response.status_code == 422


# --- admin: the hypothesis gate on fix_ready ---


def _add_hypothesis(client, admin_auth_headers, ticket_id, text="гипотеза"):
    return client.post(
        f"/admin/tickets/{ticket_id}/hypotheses", json={"text": text}, headers=admin_auth_headers
    ).json()["hypotheses"][-1]["id"]


def _set_verdict(client, admin_auth_headers, ticket_id, hyp_id, verdict, evidence=None):
    return client.patch(
        f"/admin/tickets/{ticket_id}/hypotheses/{hyp_id}",
        json={"verdict": verdict, "evidence": evidence},
        headers=admin_auth_headers,
    )


def test_fix_ready_blocked_with_no_hypotheses(client, admin_auth_headers, auth_headers):
    ticket_id = _create_ticket(client, auth_headers).json()["id"]

    response = client.post(
        f"/admin/tickets/{ticket_id}/events",
        json={"status": "fix_ready", "message": "готово"},
        headers=admin_auth_headers,
    )

    assert response.status_code == 409


def test_fix_ready_blocked_with_pending_hypothesis(client, admin_auth_headers, auth_headers):
    ticket_id = _create_ticket(client, auth_headers).json()["id"]
    h1 = _add_hypothesis(client, admin_auth_headers, ticket_id, "a")
    _add_hypothesis(client, admin_auth_headers, ticket_id, "b")
    _add_hypothesis(client, admin_auth_headers, ticket_id, "c")
    _set_verdict(client, admin_auth_headers, ticket_id, h1, "confirmed", "проверено")
    # b and c stay pending

    response = client.post(
        f"/admin/tickets/{ticket_id}/events",
        json={"status": "fix_ready", "message": "готово"},
        headers=admin_auth_headers,
    )

    assert response.status_code == 409


def test_fix_ready_succeeds_with_valid_hypothesis_pool(client, admin_auth_headers, auth_headers):
    ticket_id = _create_ticket(client, auth_headers).json()["id"]
    h1 = _add_hypothesis(client, admin_auth_headers, ticket_id, "a")
    h2 = _add_hypothesis(client, admin_auth_headers, ticket_id, "b")
    h3 = _add_hypothesis(client, admin_auth_headers, ticket_id, "c")
    _set_verdict(client, admin_auth_headers, ticket_id, h1, "confirmed", "воспроизвёл")
    _set_verdict(client, admin_auth_headers, ticket_id, h2, "rejected", "проверил — не подтвердилось")
    _set_verdict(client, admin_auth_headers, ticket_id, h3, "rejected", "тоже проверил — мимо")

    response = client.post(
        f"/admin/tickets/{ticket_id}/events",
        json={"status": "fix_ready", "message": "нашли и пофиксили: CORS не пускал новый origin"},
        headers=admin_auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["status"] == "fix_ready"


def test_deployed_blocked_unless_fix_ready(client, admin_auth_headers, auth_headers):
    ticket_id = _create_ticket(client, auth_headers).json()["id"]

    response = client.post(
        f"/admin/tickets/{ticket_id}/events",
        json={"status": "deployed", "message": "выкатили"},
        headers=admin_auth_headers,
    )

    assert response.status_code == 409


def test_full_ticket_lifecycle(client, admin_auth_headers, auth_headers):
    ticket_id = _create_ticket(client, auth_headers).json()["id"]

    client.post(
        f"/admin/tickets/{ticket_id}/events",
        json={"status": "investigating", "message": "разбираемся"},
        headers=admin_auth_headers,
    )

    h1 = _add_hypothesis(client, admin_auth_headers, ticket_id, "CORS")
    h2 = _add_hypothesis(client, admin_auth_headers, ticket_id, "слабая сеть")
    h3 = _add_hypothesis(client, admin_auth_headers, ticket_id, "истёкшая ссылка")
    _set_verdict(client, admin_auth_headers, ticket_id, h1, "confirmed", "origin не был разрешён в CORS бакета")
    _set_verdict(client, admin_auth_headers, ticket_id, h2, "rejected", "скорость была в норме по логам")
    _set_verdict(client, admin_auth_headers, ticket_id, h3, "rejected", "ссылка ещё час была валидна")

    fix_ready = client.post(
        f"/admin/tickets/{ticket_id}/events",
        json={"status": "fix_ready", "message": "добавили origin в CORS бакета"},
        headers=admin_auth_headers,
    )
    assert fix_ready.status_code == 201

    deployed = client.post(
        f"/admin/tickets/{ticket_id}/events",
        json={"status": "deployed", "message": "выкатили на прод, проверили — грузится"},
        headers=admin_auth_headers,
    )
    assert deployed.status_code == 201
    assert deployed.json()["status"] == "deployed"
    assert len(deployed.json()["events"]) == 4  # new, investigating, fix_ready, deployed
