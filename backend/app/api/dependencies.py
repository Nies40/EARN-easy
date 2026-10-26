from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.email import EmailSender
from app.modules.auth import service
from app.modules.users.models import User


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_email_sender(request: Request) -> EmailSender:
    return request.app.state.email_sender


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as db:
        yield db


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> User:
    user = service.current_user(db, request.cookies.get(settings.session_cookie_name))
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return user


def get_verified_user(user: User = Depends(get_current_user)) -> User:
    if not user.email_verified:
        raise HTTPException(
            status_code=403, detail="Verify your email to access this feature."
        )
    return user
