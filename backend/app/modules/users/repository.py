from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.users.models import User


def find_by_identifier(db: Session, identifier: str, *, for_update: bool = False) -> User | None:
    normalized = identifier.strip().lower()
    query = select(User).where(or_(User.email == normalized, User.username == normalized))
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.scalar(query)


def lock_user(db: Session, user_id: UUID) -> User | None:
    return db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def registration_exists(db: Session, email: str, username: str | None) -> bool:
    conditions = [User.email == email]
    if username is not None:
        conditions.append(User.username == username)
    return db.scalar(select(User.id).where(or_(*conditions)).limit(1)) is not None
