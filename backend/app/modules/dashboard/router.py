from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_verified_user
from app.modules.auth.schemas import CurrentUserResponse, PublicUser
from app.modules.users.models import User

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard", response_model=CurrentUserResponse)
def dashboard(user: Annotated[User, Depends(get_verified_user)]) -> CurrentUserResponse:
    return CurrentUserResponse(user=PublicUser.model_validate(user))
