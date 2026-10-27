from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_app_settings, get_current_user, get_db
from app.api.rate_limit import RATE_LIMIT_RESPONSES
from app.core.config import Settings
from app.modules.auth import service
from app.modules.auth.schemas import (
    AuthResponse,
    CurrentUserResponse,
    EmailRequest,
    LoginRequest,
    MessageResponse,
    PasswordResetRequest,
    PublicUser,
    SignupRequest,
    TokenRequest,
)
from app.modules.auth.tokens import InvalidTokenError
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


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


@router.post(
    "/signup", response_model=AuthResponse, status_code=201, responses=RATE_LIMIT_RESPONSES
)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> AuthResponse:
    try:
        user, token, _message = service.register(
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


@router.post("/login", response_model=AuthResponse, responses=RATE_LIMIT_RESPONSES)
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
    _clear_session_cookie(response, settings)
    return MessageResponse(message="Signed out.")


@router.post(
    "/email-verification/request",
    response_model=MessageResponse,
    status_code=202,
    responses=RATE_LIMIT_RESPONSES,
)
def request_verification(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> MessageResponse:
    try:
        service.request_verification(db, user, settings)
    except service.EmailCooldownError as error:
        raise HTTPException(
            status_code=429,
            detail="Please wait before requesting another verification email.",
            headers={"Retry-After": str(settings.auth_email_cooldown_seconds)},
        ) from error
    return MessageResponse(message="If verification is needed, an email has been requested.")


@router.post(
    "/email-verification/confirm", response_model=MessageResponse, responses=RATE_LIMIT_RESPONSES
)
def confirm_verification(payload: TokenRequest, db: Session = Depends(get_db)) -> MessageResponse:
    try:
        service.confirm_verification(db, payload.token)
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=400, detail="This link is invalid or has expired."
        ) from error
    return MessageResponse(message="Email verified. Your account can now access the dashboard.")


@router.post(
    "/password/forgot",
    response_model=MessageResponse,
    status_code=202,
    responses=RATE_LIMIT_RESPONSES,
)
def forgot_password(
    payload: EmailRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> MessageResponse:
    service.request_password_reset(db, str(payload.email), settings)
    return MessageResponse(
        message="If an account matches that email, a reset email has been requested."
    )


@router.post("/password/reset", response_model=MessageResponse, responses=RATE_LIMIT_RESPONSES)
def reset_password(
    payload: PasswordResetRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> MessageResponse:
    try:
        service.reset_password(db, payload.token, payload.password)
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=400, detail="This link is invalid or has expired."
        ) from error
    _clear_session_cookie(response, settings)
    return MessageResponse(message="Password reset. Sign in with your new password.")
