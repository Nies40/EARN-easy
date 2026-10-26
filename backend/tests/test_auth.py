from datetime import UTC, datetime, timedelta

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import get_db
from app.core.config import Settings
from app.core.rate_limit import RedisRateLimiter
from app.core.security import hash_session_token
from app.main import create_app
from app.modules.auth.models import UserSession
from app.modules.users.models import User


def test_signup_creates_account_and_authenticated_session(client, db, signup_payload, settings):
    response = client.post("/api/signup", json=signup_payload)

    assert response.status_code == 201
    user = response.json()["user"]
    assert user["name"] == "Jane Doe"
    assert user["email_verified"] is False
    assert "password" not in user
    assert "password_hash" not in user
    saved_user = db.scalar(select(User))
    assert bcrypt.checkpw(signup_payload["password"].encode(), saved_user.password_hash.encode())

    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=604800" in cookie
    token = client.cookies.get(settings.session_cookie_name)
    saved_session = db.scalar(select(UserSession))
    assert saved_session.token_hash == hash_session_token(token)
    assert token != saved_session.token_hash
    assert client.get("/api/me").json()["user"]["id"] == user["id"]


def test_signup_accepts_only_the_required_brief_fields(client):
    response = client.post(
        "/api/signup",
        json={"name": "Jane Doe", "email": "jane@example.com", "password": "strong-test-password"},
    )
    assert response.status_code == 201
    assert response.json()["user"]["username"] is None
    assert response.json()["user"]["phone"] is None


def test_signup_normalizes_identifiers(client, signup_payload):
    signup_payload.update(name=" Jane Doe ", email=" JANE@EXAMPLE.COM ", username=" Jane_Doe ")
    response = client.post("/api/signup", json=signup_payload)
    assert response.status_code == 201
    assert response.json()["user"]["email"] == "jane@example.com"
    assert response.json()["user"]["username"] == "jane_doe"
    assert response.json()["user"]["name"] == "Jane Doe"


@pytest.mark.parametrize("field", ["email", "username"])
def test_duplicate_identifiers_are_rejected_case_insensitively(client, signup_payload, field):
    assert client.post("/api/signup", json=signup_payload).status_code == 201
    duplicate = dict(signup_payload, email="other@example.com", username="another_user")
    duplicate[field] = signup_payload[field].upper()
    assert client.post("/api/signup", json=duplicate).status_code == 409


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", " "),
        ("name", "x" * 101),
        ("email", "not-an-email"),
        ("password", "short"),
        ("password", "a" * 73),
        ("password", "😀" * 19),
        ("username", "ab"),
        ("username", "not a username"),
        ("phone", "invalid-phone"),
    ],
)
def test_invalid_signup_is_rejected(client, signup_payload, field, value):
    signup_payload[field] = value
    response = client.post("/api/signup", json=signup_payload)
    assert response.status_code == 422
    assert "input" not in response.text


def test_validation_response_does_not_echo_password(client, signup_payload):
    secret = "this-is-a-password-that-exceeds-the-bcrypt-byte-limit-" * 2
    signup_payload["password"] = secret
    response = client.post("/api/signup", json=signup_payload)
    assert response.status_code == 422
    assert secret not in response.text


@pytest.mark.parametrize("identifier", ["JANE@EXAMPLE.COM", "JANE_DOE"])
def test_login_accepts_email_or_username(client, signup_payload, identifier):
    client.post("/api/signup", json=signup_payload)
    client.post("/api/logout")
    response = client.post(
        "/api/login", json={"identifier": identifier, "password": signup_payload["password"]}
    )
    assert response.status_code == 200
    assert client.get("/api/me").status_code == 200


@pytest.mark.parametrize("identifier", ["jane_doe", "missing@example.com", "' OR 1=1 --"])
def test_incorrect_login_returns_generic_error(client, signup_payload, identifier):
    client.post("/api/signup", json=signup_payload)
    client.post("/api/logout")
    response = client.post(
        "/api/login", json={"identifier": identifier, "password": "incorrect-password"}
    )
    assert response.status_code == 401
    assert response.json() == {"error": "Incorrect email, username, or password."}
    assert "set-cookie" not in response.headers


def test_login_rejects_passwords_beyond_bcrypt_byte_limit(client):
    response = client.post("/api/login", json={"identifier": "jane_doe", "password": "😀" * 19})
    assert response.status_code == 422


def test_login_rotates_the_previous_session(client, db, signup_payload, settings):
    client.post("/api/signup", json=signup_payload)
    old_token = client.cookies.get(settings.session_cookie_name)
    response = client.post(
        "/api/login",
        json={"identifier": signup_payload["email"], "password": signup_payload["password"]},
    )
    assert response.status_code == 200
    assert client.cookies.get(settings.session_cookie_name) != old_token
    assert db.scalar(select(func.count()).select_from(UserSession)) == 1
    assert (
        client.get(
            "/api/me", headers={"Cookie": f"{settings.session_cookie_name}={old_token}"}
        ).status_code
        == 401
    )


def test_logout_revokes_session_and_clears_cookie(client, db, signup_payload, settings):
    client.post("/api/signup", json=signup_payload)
    old_token = client.cookies.get(settings.session_cookie_name)
    response = client.post("/api/logout")
    assert response.status_code == 200
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert db.scalar(select(func.count()).select_from(UserSession)) == 0
    assert (
        client.get(
            "/api/me", headers={"Cookie": f"{settings.session_cookie_name}={old_token}"}
        ).status_code
        == 401
    )


def test_logout_is_idempotent(client):
    assert client.post("/api/logout").status_code == 200


def test_expired_session_cannot_authenticate(client, db, signup_payload):
    client.post("/api/signup", json=signup_payload)
    saved_session = db.scalar(select(UserSession))
    saved_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/me").status_code == 401


def test_anonymous_user_cannot_access_account(client):
    assert client.get("/api/me").status_code == 401


def test_database_enforces_email_uniqueness(db):
    for name in ["First User", "Second User"]:
        db.add(User(name=name, email="same@example.com", password_hash="test-only-hash"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_production_cookie_is_secure(db, signup_payload, email_sender, redis_client, monkeypatch):
    # This unit test uses SQLite; real PostgreSQL role checks have integration coverage.
    monkeypatch.setattr("app.main.check_runtime_database_role", lambda *_args: None)
    production_settings = Settings(
        _env_file=None,
        app_env="production",
        app_url="https://testserver",
        allowed_hosts=["testserver"],
        smtp_tls_mode="ssl",
        smtp_from_email="no-reply@example.org",
    )
    app = create_app(
        production_settings,
        rate_limiter=RedisRateLimiter(production_settings, client=redis_client),
    )

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, base_url="https://testserver", client=("127.0.0.1", 50000)) as client:
        response = client.post("/api/signup", json=signup_payload)
        assert response.status_code == 201
        assert "Secure" in response.headers["set-cookie"]
        assert client.get("/docs").status_code == 404
        assert "Strict-Transport-Security" in response.headers
