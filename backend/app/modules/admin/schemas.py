from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    username: str | None
    phone: str | None
    is_admin: bool
    email_verified: bool
    created_at: datetime


class AdminWithdrawalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    amount: Decimal
    phone: str
    status: str
    provider: str | None
    provider_reference: str | None
    admin_note: str | None
    created_at: datetime
    processed_at: datetime | None


class AdminStatsResponse(BaseModel):
    total_users: int
    total_revenue: float
    total_withdrawals: float
    pending_withdrawals: int
    total_credits_earned: int


class WithdrawalActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = None