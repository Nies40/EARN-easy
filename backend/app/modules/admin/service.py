from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.admin.schemas import AdminStatsResponse, AdminUserResponse
from app.modules.users.models import User
from app.modules.wallet.models import Transaction, Withdrawal
from app.modules.credits.models import CreditTransaction


def list_users(db: Session) -> list[User]:
    return db.scalars(select(User).order_by(User.created_at.desc())).all()


def list_withdrawals(db: Session, status: str | None = None) -> list[Withdrawal]:
    query = select(Withdrawal).order_by(Withdrawal.created_at.desc())
    if status:
        query = query.where(Withdrawal.status == status)
    return db.scalars(query).all()


def approve_withdrawal(db: Session, withdrawal_id: UUID, note: str | None = None) -> Withdrawal:
    withdrawal = db.scalar(select(Withdrawal).where(Withdrawal.id == withdrawal_id))
    if withdrawal is None:
        raise ValueError("Withdrawal not found.")
    if withdrawal.status != "pending":
        raise ValueError("Withdrawal is not pending.")
    withdrawal.status = "approved"
    withdrawal.admin_note = note
    withdrawal.processed_at = datetime.now(UTC)
    db.commit()
    db.refresh(withdrawal)
    return withdrawal


def reject_withdrawal(db: Session, withdrawal_id: UUID, note: str | None = None) -> Withdrawal:
    withdrawal = db.scalar(select(Withdrawal).where(Withdrawal.id == withdrawal_id))
    if withdrawal is None:
        raise ValueError("Withdrawal not found.")
    if withdrawal.status != "pending":
        raise ValueError("Withdrawal is not pending.")
    # Refund the balance
    from app.modules.wallet.models import Wallet
    wallet = db.scalar(select(Wallet).where(Wallet.user_id == withdrawal.user_id))
    if wallet:
        wallet.balance += withdrawal.amount
    withdrawal.status = "rejected"
    withdrawal.admin_note = note
    withdrawal.processed_at = datetime.now(UTC)
    db.commit()
    db.refresh(withdrawal)
    return withdrawal


def get_stats(db: Session) -> AdminStatsResponse:
    total_users = db.scalar(select(func.count(User.id))) or 0
    total_revenue = float(
        db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.type == "deposit", Transaction.status == "completed"
            )
        ) or 0
    )
    total_withdrawals = float(
        db.scalar(
            select(func.coalesce(func.sum(Withdrawal.amount), 0)).where(
                Withdrawal.status == "completed"
            )
        ) or 0
    )
    pending_withdrawals = db.scalar(
        select(func.count(Withdrawal.id)).where(Withdrawal.status == "pending")
    ) or 0
    total_credits_earned = db.scalar(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
            CreditTransaction.source == "task"
        )
    ) or 0
    return AdminStatsResponse(
        total_users=total_users,
        total_revenue=total_revenue,
        total_withdrawals=total_withdrawals,
        pending_withdrawals=pending_withdrawals,
        total_credits_earned=total_credits_earned,
    )