from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select, update

from app.core import security
from app.modules.auth import service, tokens
from app.modules.auth.models import EmailVerificationToken, PasswordResetToken, UserSession
from app.modules.auth.schemas import SignupRequest
from app.modules.users.models import User

pytestmark = pytest.mark.postgres


def token_from_message(message):
    link = next(line for line in message.body.splitlines() if line.startswith("http"))
    return parse_qs(urlsplit(link).fragment)["token"][0]


def create_account(factory, settings, signup_payload):
    with factory() as db:
        user, _, message = service.register(db, SignupRequest(**signup_payload), settings, None)
        return user.id, token_from_message(message)


def test_concurrent_verification_only_succeeds_once(pg_factory, settings, signup_payload):
    user_id, token = create_account(pg_factory, settings, signup_payload)
    barrier = Barrier(2)

    def verify():
        barrier.wait(timeout=5)
        with pg_factory() as db:
            try:
                service.confirm_verification(db, token)
            except tokens.InvalidTokenError:
                return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: verify(), range(2)))
    assert sorted(results) == [False, True]
    with pg_factory() as db:
        assert db.get(User, user_id).email_verified


def test_concurrent_password_resets_only_consume_the_token_once(
    pg_factory, settings, signup_payload
):
    user_id, _ = create_account(pg_factory, settings, signup_payload)
    with pg_factory() as db:
        message = service.request_password_reset(db, signup_payload["email"], settings)
    token = token_from_message(message)
    barrier = Barrier(2)

    def reset(password):
        barrier.wait(timeout=5)
        with pg_factory() as db:
            try:
                service.reset_password(db, token, password)
            except tokens.InvalidTokenError:
                return None
        return password

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reset, ["first-new-password", "second-new-password"]))
    winners = [password for password in results if password is not None]
    assert len(winners) == 1
    with pg_factory() as db:
        assert security.verify_password(winners[0], db.get(User, user_id).password_hash)
        assert db.scalar(select(func.count()).select_from(UserSession)) == 0
        saved = db.get(PasswordResetToken, security.hash_account_token(token))
        assert saved.used_at is not None


def test_concurrent_resends_enforce_the_per_account_cooldown(pg_factory, settings, signup_payload):
    user_id, _ = create_account(pg_factory, settings, signup_payload)
    with pg_factory() as db:
        db.execute(
            update(EmailVerificationToken).values(
                created_at=datetime.now(UTC) - timedelta(seconds=120)
            )
        )
        db.commit()
    barrier = Barrier(2)

    def resend():
        barrier.wait(timeout=5)
        with pg_factory() as db:
            try:
                return service.request_verification(db, db.get(User, user_id), settings)
            except service.EmailCooldownError:
                return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: resend(), range(2)))
    assert sum(message is not None for message in results) == 1
    with pg_factory() as db:
        assert db.scalar(select(func.count()).select_from(EmailVerificationToken)) == 1


def test_reset_revokes_a_session_created_by_an_in_flight_old_password_login(
    pg_factory, settings, signup_payload, monkeypatch
):
    create_account(pg_factory, settings, signup_payload)
    with pg_factory() as db:
        message = service.request_password_reset(db, signup_payload["email"], settings)
    reset_token = token_from_message(message)
    comparing = Event()
    release_login = Event()
    resetting = Event()
    original_verify = security.verify_password
    original_lock = tokens.lock_user

    def paused_verify(password, password_hash):
        comparing.set()
        assert release_login.wait(timeout=5)
        return original_verify(password, password_hash)

    def sign_in():
        with pg_factory() as db:
            return service.login(
                db, signup_payload["email"], signup_payload["password"], settings, None
            )[1]

    def observed_lock(db, user_id):
        resetting.set()
        return original_lock(db, user_id)

    def reset():
        with pg_factory() as db:
            service.reset_password(db, reset_token, "new-password-after-race")

    monkeypatch.setattr(security, "verify_password", paused_verify)
    monkeypatch.setattr(tokens, "lock_user", observed_lock)
    with ThreadPoolExecutor(max_workers=2) as executor:
        login_future = executor.submit(sign_in)
        try:
            assert comparing.wait(timeout=5)
            reset_future = executor.submit(reset)
            assert resetting.wait(timeout=5)
            # The reset must wait for the login's user-row lock, then revoke its session.
            with pytest.raises(TimeoutError):
                reset_future.result(timeout=0.2)
        finally:
            release_login.set()
        login_token = login_future.result(timeout=5)
        reset_future.result(timeout=5)
    with pg_factory() as db:
        assert service.current_user(db, login_token) is None
        assert db.scalar(select(func.count()).select_from(UserSession)) == 0
