from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import bcrypt
import pytest
from sqlalchemy import func, select, update

from app.core.security import generate_session_token, hash_account_token, hash_session_token
from app.modules.auth.models import EmailVerificationToken, PasswordResetToken, UserSession
from app.modules.users.models import User


def email_token(email_sender) -> str:
    email_sender.deliver_pending()
    link = next(
        line for line in email_sender.messages[-1].body.splitlines() if line.startswith("http")
    )
    return parse_qs(urlsplit(link).fragment)["token"][0]


def allow_another_email(db, model) -> None:
    db.execute(update(model).values(created_at=datetime.now(UTC) - timedelta(seconds=120)))
    db.commit()


def test_signup_emails_a_hashed_expiring_verification_token(
    client, db, signup_payload, email_sender, settings
):
    response = client.post("/api/signup", json=signup_payload)
    assert response.status_code == 201
    email_sender.deliver_pending()
    assert len(email_sender.messages) == 1
    message = email_sender.messages[0]
    assert message.recipient == signup_payload["email"]
    assert message.subject == "Verify your Easyearn email"
    assert "http://testserver/verify-email#token=" in message.body
    token = email_token(email_sender)
    saved = db.get(EmailVerificationToken, hash_account_token(token))
    assert saved is not None and saved.used_at is None
    assert (
        saved.expires_at - saved.created_at
    ).total_seconds() == settings.email_verification_ttl_seconds
    assert token not in response.text
    assert token not in repr(message)


def test_unverified_account_has_limited_access(client, signup_payload):
    client.post("/api/signup", json=signup_payload)
    assert client.get("/api/me").status_code == 200
    assert client.get("/api/dashboard").status_code == 403
    assert (
        client.post(
            "/api/login",
            json={"identifier": signup_payload["email"], "password": signup_payload["password"]},
        ).status_code
        == 200
    )


def test_verification_unlocks_dashboard_without_replacing_session(
    client, signup_payload, email_sender
):
    client.post("/api/signup", json=signup_payload)
    response = client.post(
        "/api/email-verification/confirm", json={"token": email_token(email_sender)}
    )
    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    assert client.get("/api/me").json()["user"]["email_verified"] is True
    assert client.get("/api/dashboard").status_code == 200


def test_verification_is_single_use(client, db, signup_payload, email_sender):
    client.post("/api/signup", json=signup_payload)
    token = email_token(email_sender)
    assert client.post("/api/email-verification/confirm", json={"token": token}).status_code == 200
    assert db.get(EmailVerificationToken, hash_account_token(token)).used_at is not None
    assert client.post("/api/email-verification/confirm", json={"token": token}).status_code == 400


def test_verification_does_not_require_or_create_a_session(client, signup_payload, email_sender):
    client.post("/api/signup", json=signup_payload)
    token = email_token(email_sender)
    client.post("/api/logout")
    response = client.post("/api/email-verification/confirm", json={"token": token})
    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    assert client.get("/api/dashboard").status_code == 401


def test_expired_verification_does_not_change_account(client, db, signup_payload, email_sender):
    client.post("/api/signup", json=signup_payload)
    token = email_token(email_sender)
    db.execute(
        update(EmailVerificationToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.commit()
    assert client.post("/api/email-verification/confirm", json={"token": token}).status_code == 400
    assert client.get("/api/me").json()["user"]["email_verified"] is False


def test_verification_resend_has_an_authenticated_cooldown(client, signup_payload, email_sender):
    client.post("/api/signup", json=signup_payload)
    response = client.post("/api/email-verification/request")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    email_sender.deliver_pending()
    assert len(email_sender.messages) == 1


def test_resend_replaces_the_previous_verification_token(client, db, signup_payload, email_sender):
    client.post("/api/signup", json=signup_payload)
    old_token = email_token(email_sender)
    allow_another_email(db, EmailVerificationToken)
    assert client.post("/api/email-verification/request").status_code == 202
    email_sender.deliver_pending()
    assert len(email_sender.messages) == 2
    new_token = email_token(email_sender)
    assert new_token != old_token
    assert (
        client.post("/api/email-verification/confirm", json={"token": old_token}).status_code == 400
    )
    assert (
        client.post("/api/email-verification/confirm", json={"token": new_token}).status_code == 200
    )


def test_verified_accounts_do_not_receive_another_verification_email(
    client, signup_payload, email_sender
):
    client.post("/api/signup", json=signup_payload)
    client.post("/api/email-verification/confirm", json={"token": email_token(email_sender)})
    assert client.post("/api/email-verification/request").status_code == 202
    assert len(email_sender.messages) == 1


def test_anonymous_verification_resend_is_rejected(client, email_sender):
    assert client.post("/api/email-verification/request").status_code == 401
    assert email_sender.messages == []


def test_password_requests_have_identical_public_responses_and_a_silent_cooldown(
    client, db, signup_payload, email_sender, settings
):
    client.post("/api/signup", json=signup_payload)
    known = client.post("/api/password/forgot", json={"email": " JANE@EXAMPLE.COM "})
    token = email_token(email_sender)
    unknown = client.post("/api/password/forgot", json={"email": "missing@example.com"})
    throttled = client.post("/api/password/forgot", json={"email": signup_payload["email"]})
    assert known.status_code == unknown.status_code == throttled.status_code == 202
    assert known.json() == unknown.json() == throttled.json()
    assert len(email_sender.messages) == 2
    assert token not in known.text
    saved = db.get(PasswordResetToken, hash_account_token(token))
    assert (
        saved.expires_at - saved.created_at
    ).total_seconds() == settings.password_reset_ttl_seconds


def test_reset_changes_password_revokes_all_account_sessions_and_preserves_unverified_status(
    client, db, signup_payload, email_sender, settings
):
    client.post("/api/signup", json=signup_payload)
    first_token = client.cookies.get(settings.session_cookie_name)
    user = db.scalar(select(User))
    second_token = generate_session_token()
    db.add(
        UserSession(
            token_hash=hash_session_token(second_token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()
    client.post("/api/password/forgot", json={"email": signup_payload["email"]})
    token = email_token(email_sender)
    new_password = "a-new-long-password"
    response = client.post("/api/password/reset", json={"token": token, "password": new_password})
    assert response.status_code == 200
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert db.scalar(select(func.count()).select_from(UserSession)) == 0
    assert db.get(PasswordResetToken, hash_account_token(token)).used_at is not None
    for session_token in (first_token, second_token):
        assert (
            client.get(
                "/api/me", headers={"Cookie": f"{settings.session_cookie_name}={session_token}"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/login",
            json={"identifier": signup_payload["email"], "password": signup_payload["password"]},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/login", json={"identifier": signup_payload["email"], "password": new_password}
        ).status_code
        == 200
    )
    assert client.get("/api/me").json()["user"]["email_verified"] is False
    assert bcrypt.checkpw(new_password.encode(), db.scalar(select(User)).password_hash.encode())
    assert (
        client.post(
            "/api/password/reset", json={"token": token, "password": "another-new-password"}
        ).status_code
        == 400
    )


def test_another_reset_request_supersedes_the_previous_token(
    client, db, signup_payload, email_sender
):
    client.post("/api/signup", json=signup_payload)
    client.post("/api/password/forgot", json={"email": signup_payload["email"]})
    old_token = email_token(email_sender)
    allow_another_email(db, PasswordResetToken)
    client.post("/api/password/forgot", json={"email": signup_payload["email"]})
    new_token = email_token(email_sender)
    assert old_token != new_token
    assert (
        client.post(
            "/api/password/reset", json={"token": old_token, "password": "new-long-password"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/password/reset", json={"token": new_token, "password": "new-long-password"}
        ).status_code
        == 200
    )


def test_expired_reset_does_not_change_password_or_revoke_sessions(
    client, db, signup_payload, email_sender
):
    client.post("/api/signup", json=signup_payload)
    original_hash = db.scalar(select(User)).password_hash
    client.post("/api/password/forgot", json={"email": signup_payload["email"]})
    token = email_token(email_sender)
    db.execute(
        update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db.commit()
    assert (
        client.post(
            "/api/password/reset", json={"token": token, "password": "a-new-long-password"}
        ).status_code
        == 400
    )
    assert db.scalar(select(User)).password_hash == original_hash
    assert client.get("/api/me").status_code == 200


def test_tokens_cannot_be_used_for_a_different_purpose(client, signup_payload, email_sender):
    client.post("/api/signup", json=signup_payload)
    verification_token = email_token(email_sender)
    client.post("/api/password/forgot", json={"email": signup_payload["email"]})
    reset_token = email_token(email_sender)
    assert (
        client.post("/api/email-verification/confirm", json={"token": reset_token}).status_code
        == 400
    )
    assert (
        client.post(
            "/api/password/reset",
            json={"token": verification_token, "password": "new-long-password"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/email-verification/confirm", json={"token": verification_token}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("password", ["short", "😀" * 19])
def test_invalid_new_password_does_not_consume_token(
    client, signup_payload, email_sender, password
):
    client.post("/api/signup", json=signup_payload)
    client.post("/api/password/forgot", json={"email": signup_payload["email"]})
    token = email_token(email_sender)
    response = client.post("/api/password/reset", json={"token": token, "password": password})
    assert response.status_code == 422
    assert token not in response.text and password not in response.text
    assert (
        client.post(
            "/api/password/reset", json={"token": token, "password": "valid-new-password"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("path", ["/api/email-verification/confirm", "/api/password/reset"])
def test_link_visits_do_not_consume_tokens(client, path):
    assert client.get(path).status_code == 405


@pytest.mark.parametrize(
    "path", ["/api/password/forgot", "/api/password/reset", "/api/email-verification/confirm"]
)
def test_recovery_endpoints_reject_cross_origin_requests(client, path):
    assert (
        client.post(path, json={}, headers={"Origin": "https://attacker.example"}).status_code
        == 403
    )


def test_reset_does_not_revoke_another_accounts_session(
    client, db, signup_payload, email_sender, settings
):
    client.post("/api/signup", json=signup_payload)
    other_user = User(name="Other User", email="other@example.com", password_hash="not-used-here")
    db.add(other_user)
    db.flush()
    other_token = generate_session_token()
    db.add(
        UserSession(
            token_hash=hash_session_token(other_token),
            user_id=other_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()
    client.post("/api/password/forgot", json={"email": signup_payload["email"]})
    response = client.post(
        "/api/password/reset", json={"token": email_token(email_sender), "password": "new-password"}
    )
    assert response.status_code == 200
    assert db.get(UserSession, hash_session_token(other_token)) is not None
    account = client.get(
        "/api/me", headers={"Cookie": f"{settings.session_cookie_name}={other_token}"}
    )
    assert account.status_code == 200
    assert account.json()["user"]["email"] == "other@example.com"


def test_reset_keeps_an_existing_email_verification(client, db, signup_payload, email_sender):
    client.post("/api/signup", json=signup_payload)
    client.post("/api/email-verification/confirm", json={"token": email_token(email_sender)})
    verified_at = db.scalar(select(User)).email_verified_at
    client.post("/api/password/forgot", json={"email": signup_payload["email"]})
    response = client.post(
        "/api/password/reset", json={"token": email_token(email_sender), "password": "new-password"}
    )
    assert response.status_code == 200
    assert db.scalar(select(User)).email_verified_at == verified_at


@pytest.mark.parametrize("path", ["/api/email-verification/confirm", "/api/password/reset"])
def test_unknown_tokens_return_a_generic_error(client, path):
    body = {"token": "x" * 43}
    if path.endswith("/reset"):
        body["password"] = "new-long-password"
    response = client.post(path, json=body)
    assert response.status_code == 400
    assert response.json() == {"error": "This link is invalid or has expired."}


def test_openapi_documents_the_account_flows(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in (
        "/api/email-verification/request",
        "/api/email-verification/confirm",
        "/api/password/forgot",
        "/api/password/reset",
    ):
        assert "post" in paths[path]
    assert "get" in paths["/api/dashboard"]
