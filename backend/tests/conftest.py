import pytest

from app.auth import create_access_token, hash_password
from app.models import User


@pytest.fixture
def active_user(db_session):
    user = User(
        email="user@example.com", password_hash=hash_password("password123"), role="user", status="active"
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def auth_headers(active_user):
    return {"Authorization": f"Bearer {create_access_token(active_user.id)}"}
