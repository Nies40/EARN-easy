from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReferralResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    referral_code: str
    status: str
    referred_id: UUID | None
    bonus_amount: Decimal
    activated_at: datetime | None
    created_at: datetime


class ReferralStatsResponse(BaseModel):
    total_referrals: int
    activated_referrals: int
    pending_referrals: int
    total_bonus_earned: Decimal
    referral_code: str
    referral_link: str


class EarningsTrendPoint(BaseModel):
    month: str
    amount: float


class ReferralTrendPoint(BaseModel):
    month: str
    count: int