from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_app_settings, get_current_user, get_db
from app.core.config import Settings
from app.modules.credits import service
from app.modules.credits.schemas import (
    ConvertCreditsRequest,
    ConvertCreditsResponse,
    CreditBalanceResponse,
    CreditTransactionResponse,
)
from app.modules.users.models import User

router = APIRouter(tags=["Credits"])


@router.get("/credits", response_model=CreditBalanceResponse)
def get_credits(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreditBalanceResponse:
    balance = service.get_or_create_balance(db, user.id)
    return CreditBalanceResponse.model_validate(balance)


@router.post("/credits/convert", response_model=ConvertCreditsResponse)
def convert_credits(
    payload: ConvertCreditsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> ConvertCreditsResponse:
    try:
        result = service.convert_credits(db, user.id, payload.credits, settings)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return ConvertCreditsResponse(**result)


@router.get("/credits/transactions", response_model=list[CreditTransactionResponse])
def list_credit_transactions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CreditTransactionResponse]:
    txns = service.get_transactions(db, user.id)
    return [CreditTransactionResponse.model_validate(t) for t in txns]