from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_app_settings, get_current_user, get_db, get_verified_user
from app.core.config import Settings
from app.modules.auth.schemas import CurrentUserResponse, PublicUser
from app.modules.credits import service as credits_service
from app.modules.referrals import service as referrals_service
from app.modules.users.models import User
from app.modules.wallet import service as wallet_service
from pydantic import BaseModel

router = APIRouter(tags=["Dashboard"])


class OverviewResponse(BaseModel):
    user: PublicUser
    wallet: dict
    credits: dict
    referrals: dict
    earnings_trend: list[dict]
    referral_trend: list[dict]
    this_month_earned: float
    this_month_withdrawn: float


@router.get("/dashboard", response_model=CurrentUserResponse)
def dashboard(user: Annotated[User, Depends(get_verified_user)]) -> CurrentUserResponse:
    return CurrentUserResponse(user=PublicUser.model_validate(user))


@router.get("/overview", response_model=OverviewResponse)
def overview(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> OverviewResponse:
    wallet = wallet_service.get_or_create_wallet(db, user.id)
    credit_balance = credits_service.get_or_create_balance(db, user.id)
    referral_stats = referrals_service.get_stats(db, user.id, settings)
    earnings_trend = wallet_service.get_earnings_trend(db, user.id)
    referral_trend = referrals_service.get_referral_trend(db, user.id)

    # This month's stats
    now = datetime.now(UTC)
    month_prefix = now.strftime("%Y-%m")
    txns = wallet_service.get_transactions(db, user.id, limit=200)
    this_month_earned = sum(
        float(t.amount) for t in txns
        if t.type == "earning" and t.created_at and t.created_at.strftime("%Y-%m") == month_prefix
    )
    this_month_withdrawn = sum(
        float(t.amount) for t in txns
        if t.type == "withdrawal" and t.created_at and t.created_at.strftime("%Y-%m") == month_prefix
    )

    return OverviewResponse(
        user=PublicUser.model_validate(user),
        wallet={
            "balance": float(wallet.balance),
            "total_earned": float(wallet.total_earned),
            "total_withdrawn": float(wallet.total_withdrawn),
        },
        credits={
            "balance": credit_balance.balance,
            "total_earned": credit_balance.total_earned,
        },
        referrals=referral_stats,
        earnings_trend=earnings_trend,
        referral_trend=referral_trend,
        this_month_earned=this_month_earned,
        this_month_withdrawn=this_month_withdrawn,
    )
