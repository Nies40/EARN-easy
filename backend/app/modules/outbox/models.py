import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailJob(Base):
    __tablename__ = "email_outbox"
    __table_args__ = (
        CheckConstraint("purpose IN ('verification', 'password_reset')", name="purpose"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'sent', 'failed', 'discarded')", name="status"
        ),
        CheckConstraint("attempts >= 0", name="attempts"),
        CheckConstraint(
            "(status IN ('pending', 'processing') AND encrypted_payload IS NOT NULL "
            "AND completed_at IS NULL) OR (status IN ('sent', 'failed', 'discarded') "
            "AND encrypted_payload IS NULL AND completed_at IS NOT NULL)",
            name="payload_lifecycle",
        ),
        CheckConstraint(
            "(status = 'processing' AND lease_id IS NOT NULL AND leased_until IS NOT NULL) "
            "OR (status <> 'processing' AND lease_id IS NULL AND leased_until IS NULL)",
            name="lease_lifecycle",
        ),
        UniqueConstraint("purpose", "token_hash"),
        Index("ix_email_outbox_pending", "status", "next_attempt_at"),
        Index("ix_email_outbox_leases", "status", "leased_until"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64))
    key_id: Mapped[str] = mapped_column(String(64))
    encrypted_payload: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lease_id: Mapped[uuid.UUID | None]
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
