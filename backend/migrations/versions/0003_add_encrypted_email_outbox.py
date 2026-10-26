"""Add encrypted, transactional email jobs with recoverable worker leases.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_id", sa.Uuid(), nullable=True),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(40), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "purpose IN ('verification', 'password_reset')", name=op.f("ck_email_outbox_purpose")
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'sent', 'failed', 'discarded')",
            name=op.f("ck_email_outbox_status"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_email_outbox_attempts")),
        sa.CheckConstraint(
            "(status IN ('pending', 'processing') AND encrypted_payload IS NOT NULL "
            "AND completed_at IS NULL) OR (status IN ('sent', 'failed', 'discarded') "
            "AND encrypted_payload IS NULL AND completed_at IS NOT NULL)",
            name=op.f("ck_email_outbox_payload_lifecycle"),
        ),
        sa.CheckConstraint(
            "(status = 'processing' AND lease_id IS NOT NULL AND leased_until IS NOT NULL) "
            "OR (status <> 'processing' AND lease_id IS NULL AND leased_until IS NULL)",
            name=op.f("ck_email_outbox_lease_lifecycle"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_email_outbox_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_outbox")),
        sa.UniqueConstraint("purpose", "token_hash", name=op.f("uq_email_outbox_purpose")),
    )
    for column in ("user_id", "expires_at", "completed_at"):
        op.create_index(op.f(f"ix_email_outbox_{column}"), "email_outbox", [column])
    op.create_index("ix_email_outbox_pending", "email_outbox", ["status", "next_attempt_at"])
    op.create_index("ix_email_outbox_leases", "email_outbox", ["status", "leased_until"])


def downgrade() -> None:
    op.drop_table("email_outbox")
