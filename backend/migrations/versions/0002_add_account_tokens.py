"""Add expiring, single-use verification and password reset tokens.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("email_verification_tokens", "password_reset_tokens"):
        op.create_table(
            table,
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                ondelete="CASCADE",
                name=op.f(f"fk_{table}_user_id_users"),
            ),
            sa.PrimaryKeyConstraint("token_hash", name=op.f(f"pk_{table}")),
        )
        op.create_index(op.f(f"ix_{table}_user_id"), table, ["user_id"])
        op.create_index(op.f(f"ix_{table}_expires_at"), table, ["expires_at"])


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_table("email_verification_tokens")
