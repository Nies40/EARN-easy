from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.modules.users.models import User
from app.modules.wallet import service
from app.modules.wallet.schemas import (
    TransactionResponse,
    WalletResponse,
    WithdrawalRequest,
    WithdrawalResponse,
)

router = APIRouter(tags=["Wallet"])


@router.get("/wallet", response_model=WalletResponse)
def get_wallet(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WalletResponse:
    wallet = service.get_or_create_wallet(db, user.id)
    return WalletResponse.model_validate(wallet)


@router.get("/wallet/transactions", response_model=list[TransactionResponse])
def list_transactions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TransactionResponse]:
    txns = service.get_transactions(db, user.id)
    return [TransactionResponse.model_validate(t) for t in txns]


@router.post("/wallet/withdraw", response_model=WithdrawalResponse, status_code=201)
def create_withdrawal(
    payload: WithdrawalRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WithdrawalResponse:
    try:
        withdrawal = service.request_withdrawal(db, user.id, payload.amount, payload.phone)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return WithdrawalResponse.model_validate(withdrawal)


@router.get("/wallet/withdrawals", response_model=list[WithdrawalResponse])
def list_withdrawals(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WithdrawalResponse]:
    items = service.get_withdrawals(db, user.id)
    return [WithdrawalResponse.model_validate(w) for w in items]