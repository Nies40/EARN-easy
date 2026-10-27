from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.security import generate_account_token, hash_account_token
from app.modules.auth.models import EmailVerificationToken, PasswordResetToken
from app.modules.users.models import User
from app.modules.users.repository import lock_user

TokenModel = type[EmailVerificationToken] | type[PasswordResetToken]


class InvalidTokenError(Exception):
    pass


def recently_issued(db: Session, model: TokenModel, user_id: UUID, cooldown: int) -> bool:
    return (
        db.scalar(
            select(model.token_hash)
            .where(
                model.user_id == user_id,
                model.created_at > datetime.now(UTC) - timedelta(seconds=cooldown),
            )
            .limit(1)
        )
        is not None
    )


def issue(db: Session, model: TokenModel, user_id: UUID, ttl: int) -> str:
    """Caller must lock the user first. A newly issued token supersedes older ones."""
    db.execute(delete(model).where(model.user_id == user_id))
    token = generate_account_token()
    now = datetime.now(UTC)
    db.add(
        model(
            token_hash=hash_account_token(token),
            user_id=user_id,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
        )
    )
    return token


def consume(db: Session, model: TokenModel, token: str) -> User:
    token_hash = hash_account_token(token)
    user_id = db.scalar(select(model.user_id).where(model.token_hash == token_hash))
    if user_id is None:
        db.rollback()
        raise InvalidTokenError

    # All account mutations lock the user before token/session rows. This also
    # serializes resets with logins so old-password sessions cannot survive a reset.
    user = lock_user(db, user_id)
    now = datetime.now(UTC)
    consumed_user_id = db.scalar(
        update(model)
        .where(
            model.token_hash == token_hash,
            model.used_at.is_(None),
            model.expires_at > now,
        )
        .values(used_at=now)
        .returning(model.user_id)
    )
    if user is None or consumed_user_id is None:
        db.rollback()
        raise InvalidTokenError
    return user
