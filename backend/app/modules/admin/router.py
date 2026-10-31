from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_admin_user, get_db
from app.modules.admin import service
from app.modules.admin.schemas import (
    AdminStatsResponse,
    AdminUserResponse,
    AdminWithdrawalResponse,
    WithdrawalActionRequest,
)
from app.modules.users.models import User

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats", response_model=AdminStatsResponse)
def admin_stats(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminStatsResponse:
    return service.get_stats(db)


@router.get("/users", response_model=list[AdminUserResponse])
def admin_list_users(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[AdminUserResponse]:
    users = service.list_users(db)
    return [AdminUserResponse.model_validate(u) for u in users]


@router.get("/withdrawals", response_model=list[AdminWithdrawalResponse])
def admin_list_withdrawals(
    status: str | None = Query(None),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[AdminWithdrawalResponse]:
    items = service.list_withdrawals(db, status)
    return [AdminWithdrawalResponse.model_validate(w) for w in items]


@router.post("/withdrawals/{withdrawal_id}/approve", response_model=AdminWithdrawalResponse)
def admin_approve_withdrawal(
    withdrawal_id: str,
    payload: WithdrawalActionRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminWithdrawalResponse:
    try:
        w = service.approve_withdrawal(db, withdrawal_id, payload.note)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return AdminWithdrawalResponse.model_validate(w)


@router.post("/withdrawals/{withdrawal_id}/reject", response_model=AdminWithdrawalResponse)
def admin_reject_withdrawal(
    withdrawal_id: str,
    payload: WithdrawalActionRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminWithdrawalResponse:
    try:
        w = service.reject_withdrawal(db, withdrawal_id, payload.note)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return AdminWithdrawalResponse.model_validate(w)