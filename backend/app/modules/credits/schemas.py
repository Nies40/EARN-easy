from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreditBalanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    balance: int
    total_earned: int


class CreditTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount: int
    source: str
    description: str | None
    created_at: datetime


class ConvertCreditsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credits: int = Field(gt=0, description="Number of credits to convert to Ksh")


class ConvertCreditsResponse(BaseModel):
    credits_converted: int
    ksh_amount: float
    new_balance: int
    new_wallet_balance: float