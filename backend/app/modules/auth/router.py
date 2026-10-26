from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_app_settings, get_current_user, get_db
from app.core.config import Settings
from app.modules.auth import service
from app.modules.auth.schemas import (
    AuthResponse,
    CurrentUserResponse,
    LoginRequest,
    MessageResponse,
    PublicUser,
    SignupRequest,
)
from app.modules.users.models import User

router = APIRouter(tags=["Authentication"])


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


@router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> AuthResponse:
    try:
        user, token = service.register(
            db, payload, settings, request.cookies.get(settings.session_cookie_name)
        )
    except service.DuplicateAccountError as error:
        raise HTTPException(
            status_code=409, detail="That email or username is already registered."
        ) from error
    _set_session_cookie(response, token, settings)
    return AuthResponse(
        message="Account created successfully.", user=PublicUser.model_validate(user)
    )


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> AuthResponse:
    try:
        user, token = service.login(
            db,
            payload.identifier,
            payload.password,
            settings,
            request.cookies.get(settings.session_cookie_name),
        )
    except service.InvalidCredentialsError as error:
        raise HTTPException(
            status_code=401, detail="Incorrect email, username, or password."
        ) from error
    _set_session_cookie(response, token, settings)
    return AuthResponse(message="Signed in successfully.", user=PublicUser.model_validate(user))


@router.get("/me", response_model=CurrentUserResponse)
def me(user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(user=PublicUser.model_validate(user))


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> MessageResponse:
    service.logout(db, request.cookies.get(settings.session_cookie_name))
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )
    return MessageResponse(message="Signed out.")
