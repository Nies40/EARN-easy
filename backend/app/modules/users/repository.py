from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.users.models import User


def find_by_identifier(db: Session, identifier: str) -> User | None:
    normalized = identifier.strip().lower()
    return db.scalar(select(User).where(or_(User.email == normalized, User.username == normalized)))


def registration_exists(db: Session, email: str, username: str | None) -> bool:
    conditions = [User.email == email]
    if username is not None:
        conditions.append(User.username == username)
    return db.scalar(select(User.id).where(or_(*conditions)).limit(1)) is not None
