from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.wallet.models import Transaction, Wallet, Withdrawal


def get_or_create_wallet(db: Session, user_id: UUID) -> Wallet:
    wallet = db.scalar(select(Wallet).where(Wallet.user_id == user_id))
    if wallet is None:
        wallet = Wallet(user_id=user_id)
        db.add(wallet)
        db.flush()
    return wallet


def _gen_reference(prefix: str = "TXN") -> str:
    return f"{prefix}-{uuid4().hex[:12].upper()}"


def record_transaction(
    db: Session,
    wallet: Wallet,
    txn_type: str,
    amount: Decimal,
    *,
    reference: str | None = None,
    status: str = "completed",
    provider: str | None = None,
    provider_reference: str | None = None,
    description: str | None = None,
) -> Transaction:
    txn = Transaction(
        wallet_id=wallet.id,
        user_id=wallet.user_id,
        type=txn_type,
        amount=amount,
        reference=reference or _gen_reference(),
        status=status,
        provider=provider,
        provider_reference=provider_reference,
        description=description,
    )
    db.add(txn)
    return txn


def get_transactions(db: Session, user_id: UUID, limit: int = 50) -> list[Transaction]:
    return (
        db.scalars(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        .all()
    )


def request_withdrawal(db: Session, user_id: UUID, amount: Decimal, phone: str) -> Withdrawal:
    wallet = get_or_create_wallet(db, user_id)
    if wallet.balance < amount:
        raise ValueError("Insufficient wallet balance.")
    # Deduct immediately and hold as pending; refund on rejection.
    wallet.balance -= amount
    withdrawal = Withdrawal(user_id=user_id, amount=amount, phone=phone)
    db.add(withdrawal)
    record_transaction(
        db, wallet, "withdrawal", amount,
        reference=_gen_reference("WTH"),
        status="pending",
        provider="mpesa",
        description=f"Withdrawal request to {phone}",
    )
    db.commit()
    db.refresh(withdrawal)
    return withdrawal


def get_withdrawals(db: Session, user_id: UUID) -> list[Withdrawal]:
    return (
        db.scalars(
            select(Withdrawal)
            .where(Withdrawal.user_id == user_id)
            .order_by(Withdrawal.created_at.desc())
        )
        .all()
    )


def get_earnings_trend(db: Session, user_id: UUID, months: int = 6) -> list[dict]:
    """Monthly earnings for the last N months."""
    rows = db.execute(
        select(
            func.to_char(Transaction.created_at, "YYYY-MM").label("month"),
            func.sum(Transaction.amount).label("total"),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.type == "earning",
            Transaction.status == "completed",
        )
        .group_by("month")
        .order_by("month")
    ).all()
    return [{"month": r.month, "amount": float(r.total or 0)} for r in rows]