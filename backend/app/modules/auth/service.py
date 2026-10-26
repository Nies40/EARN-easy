from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.modules.auth.models import UserSession
from app.modules.auth.schemas import SignupRequest
from app.modules.users import repository
from app.modules.users.models import User


class DuplicateAccountError(Exception):
    pass


class InvalidCredentialsError(Exception):
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
) -> tuple[User, str]:
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
    db.commit()
    return user, token


def login(
    db: Session,
    identifier: str,
    password: str,
    settings: Settings,
    previous_token: str | None,
) -> tuple[User, str]:
    user = repository.find_by_identifier(db, identifier)
    password_hash = user.password_hash if user else security.DUMMY_PASSWORD_HASH
    password_matches = security.verify_password(password, password_hash)
    if user is None or not password_matches:
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
