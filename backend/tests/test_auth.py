import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers tables on Base.metadata
from app.auth import (
    InvalidTokenError,
    bootstrap_admin_user,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db import Base
from app.models import User


def test_hash_password_produces_a_verifiable_hash():
    hashed = hash_password("correct horse battery staple")

    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct horse battery staple")

    assert not verify_password("wrong password", hashed)


def test_hash_password_is_salted_differently_each_time():
    a = hash_password("same password")
    b = hash_password("same password")

    assert a != b
    assert verify_password("same password", a)
    assert verify_password("same password", b)


def test_create_and_decode_access_token_roundtrip():
    token = create_access_token(user_id="user-123", expires_minutes=5)

    payload = decode_access_token(token)

    assert payload["sub"] == "user-123"


def test_decode_access_token_rejects_expired_token():
    token = create_access_token(user_id="user-123", expires_minutes=-1)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_decode_access_token_rejects_garbage():
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-real-token")


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_bootstrap_admin_user_creates_active_admin(db_session):
    bootstrap_admin_user(db_session, email="admin@example.com", password="verysecretadmin")

    admin = db_session.query(User).filter_by(email="admin@example.com").first()
    assert admin is not None
    assert admin.role == "admin"
    assert admin.status == "active"
    assert verify_password("verysecretadmin", admin.password_hash)


def test_bootstrap_admin_user_is_idempotent(db_session):
    bootstrap_admin_user(db_session, email="admin@example.com", password="verysecretadmin")
    bootstrap_admin_user(db_session, email="admin@example.com", password="differentpassword")

    admins = db_session.query(User).filter_by(email="admin@example.com").all()
    assert len(admins) == 1
    assert verify_password("verysecretadmin", admins[0].password_hash)


def test_bootstrap_admin_user_noop_without_credentials(db_session):
    bootstrap_admin_user(db_session, email="", password="")

    assert db_session.query(User).count() == 0


def test_decode_access_token_rejects_wrong_signature():
    token = create_access_token(user_id="user-123", expires_minutes=5)
    header, payload, signature = token.split(".")
    mid = len(signature) // 2
    flipped_char = "a" if signature[mid] != "a" else "b"
    tampered_signature = signature[:mid] + flipped_char + signature[mid + 1 :]
    tampered = f"{header}.{payload}.{tampered_signature}"

    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)
