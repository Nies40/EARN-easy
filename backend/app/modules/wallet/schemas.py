from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated


class WalletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    balance: Decimal
    total_earned: Decimal
    total_withdrawn: Decimal


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    amount: Decimal
    reference: str
    status: str
    provider: str | None
    description: str | None
    created_at: datetime


class WithdrawalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, le=100000)
    phone: Annotated[str, StringConstraints(min_length=10, max_length=17, pattern=r"^\+?[0-9]{7,16}$")]


class WithdrawalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount: Decimal
    phone: str
    status: str
    created_at: datetime
    processed_at: datetime | None


class DepositRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, le=100000)
    phone: Annotated[str, StringConstraints(min_length=10, max_length=17, pattern=r"^\+?[0-9]{7,16}$")]


class DepositResponse(BaseModel):
    id: UUID
    amount: Decimal
    phone: str
    status: str
    reference: str
    message: str