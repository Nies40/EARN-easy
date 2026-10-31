from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.credits.models import CreditBalance, CreditTransaction
from app.modules.wallet import service as wallet_service


def get_or_create_balance(db: Session, user_id: UUID) -> CreditBalance:
    balance = db.scalar(select(CreditBalance).where(CreditBalance.user_id == user_id))
    if balance is None:
        balance = CreditBalance(user_id=user_id)
        db.add(balance)
        db.flush()
    return balance


def earn_credits(
    db: Session,
    user_id: UUID,
    amount: int,
    source: str,
    *,
    task_id: UUID | None = None,
    description: str | None = None,
) -> CreditBalance:
    balance = get_or_create_balance(db, user_id)
    balance.balance += amount
    balance.total_earned += amount
    db.add(
        CreditTransaction(
            user_id=user_id,
            amount=amount,
            source=source,
            task_id=task_id,
            description=description,
        )
    )
    return balance


def convert_credits(db: Session, user_id: UUID, credits: int, settings: Settings) -> dict:
    balance = get_or_create_balance(db, user_id)
    if balance.balance < credits:
        raise ValueError("Insufficient credits.")
    ksh_amount = Decimal(credits) / Decimal(settings.credits_per_ksh)
    balance.balance -= credits
    wallet = wallet_service.get_or_create_wallet(db, user_id)
    wallet.balance += ksh_amount
    wallet.total_earned += ksh_amount
    wallet_service.record_transaction(
        db,
        wallet,
        "credit_conversion",
        ksh_amount,
        description=f"Converted {credits} credits to Ksh",
    )
    db.add(
        CreditTransaction(
            user_id=user_id,
            amount=-credits,
            source="conversion",
            description=f"Converted to Ksh {ksh_amount}",
        )
    )
    db.commit()
    return {
        "credits_converted": credits,
        "ksh_amount": float(ksh_amount),
        "new_balance": balance.balance,
        "new_wallet_balance": float(wallet.balance),
    }


def get_transactions(db: Session, user_id: UUID, limit: int = 50) -> list[CreditTransaction]:
    return (
        db.scalars(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .order_by(CreditTransaction.created_at.desc())
            .limit(limit)
        )
        .all()
    )