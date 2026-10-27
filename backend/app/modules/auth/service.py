from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.integrations.email import OutgoingEmail
from app.modules.auth import tokens
from app.modules.auth.emails import password_reset_email, verification_email
from app.modules.auth.models import EmailVerificationToken, PasswordResetToken, UserSession
from app.modules.auth.schemas import SignupRequest
from app.modules.outbox.service import enqueue_account_email
from app.modules.users import repository
from app.modules.users.models import User


class DuplicateAccountError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class EmailCooldownError(Exception):
    pass


def _create_session(db: Session, user: User, settings: Settings, previous_token: str | None) -> str:
    if previous_token:
        db.execute(
            delete(UserSession).where(
                UserSession.token_hash == security.hash_session_token(previous_token)
            )
        )
    token = security.generate_session_token()
    db.add(
        UserSession(
            token_hash=security.hash_session_token(token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    return token


def register(
    db: Session, payload: SignupRequest, settings: Settings, previous_token: str | None
) -> tuple[User, str, OutgoingEmail]:
    if repository.registration_exists(db, str(payload.email), payload.username):
        raise DuplicateAccountError

    user = User(
        name=payload.name,
        email=str(payload.email),
        username=payload.username,
        phone=payload.phone,
        password_hash=security.hash_password(payload.password),
    )
    db.add(user)
    try:
        # The unique database constraints also protect against concurrent duplicate signups.
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise DuplicateAccountError from error

    token = _create_session(db, user, settings, previous_token)
    verification_token = tokens.issue(
        db, EmailVerificationToken, user.id, settings.email_verification_ttl_seconds
    )
    message = verification_email(user.email, verification_token, settings)
    enqueue_account_email(
        db, settings, EmailVerificationToken, verification_token, "verification", message
    )
    db.commit()
    return user, token, message


def login(
    db: Session,
    identifier: str,
    password: str,
    settings: Settings,
    previous_token: str | None,
) -> tuple[User, str]:
    user = repository.find_by_identifier(db, identifier, for_update=True)
    password_hash = user.password_hash if user else security.DUMMY_PASSWORD_HASH
    password_matches = security.verify_password(password, password_hash)
    if user is None or not password_matches:
        db.rollback()
        raise InvalidCredentialsError

    token = _create_session(db, user, settings, previous_token)
    db.commit()
    return user, token


def current_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    return db.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == security.hash_session_token(token),
            UserSession.expires_at > datetime.now(UTC),
        )
    )


def logout(db: Session, token: str | None) -> None:
    if token:
        db.execute(
            delete(UserSession).where(UserSession.token_hash == security.hash_session_token(token))
        )
        db.commit()


def request_verification(db: Session, user: User, settings: Settings) -> OutgoingEmail | None:
    user = repository.lock_user(db, user.id)
    if user is None or user.email_verified:
        db.rollback()
        return None
    if tokens.recently_issued(
        db, EmailVerificationToken, user.id, settings.auth_email_cooldown_seconds
    ):
        db.rollback()
        raise EmailCooldownError
    token = tokens.issue(
        db, EmailVerificationToken, user.id, settings.email_verification_ttl_seconds
    )
    message = verification_email(user.email, token, settings)
    enqueue_account_email(db, settings, EmailVerificationToken, token, "verification", message)
    db.commit()
    return message


def confirm_verification(db: Session, token: str) -> None:
    user = tokens.consume(db, EmailVerificationToken, token)
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    db.commit()


def request_password_reset(db: Session, email: str, settings: Settings) -> OutgoingEmail | None:
    user = repository.find_by_identifier(db, email, for_update=True)
    if user is None or tokens.recently_issued(
        db, PasswordResetToken, user.id, settings.auth_email_cooldown_seconds
    ):
        # Deliberately use the same public response for unknown and throttled accounts.
        db.rollback()
        return None
    token = tokens.issue(db, PasswordResetToken, user.id, settings.password_reset_ttl_seconds)
    message = password_reset_email(user.email, token, settings)
    enqueue_account_email(db, settings, PasswordResetToken, token, "password_reset", message)
    db.commit()
    return message


def reset_password(db: Session, token: str, password: str) -> None:
    user = tokens.consume(db, PasswordResetToken, token)
    user.password_hash = security.hash_password(password)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    # Token consumption, password change, and revocation commit as one transaction.
    # Do not mark email verified or automatically create a replacement session.
    db.commit()
