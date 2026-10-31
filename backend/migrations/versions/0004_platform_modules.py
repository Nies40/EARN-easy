"""Add wallet, referral, credits, tasks, and admin platform modules.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.types import JSON

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- users: add admin flag and referral code ---
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("referral_code", sa.String(20), nullable=True))
    op.create_index(op.f("ix_users_referral_code"), "users", ["referral_code"], unique=True)

    # --- wallets ---
    op.create_table(
        "wallets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("balance", sa.Numeric(12, 2), server_default="0.00", nullable=False),
        sa.Column("total_earned", sa.Numeric(12, 2), server_default="0.00", nullable=False),
        sa.Column("total_withdrawn", sa.Numeric(12, 2), server_default="0.00", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_wallets_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wallets")),
        sa.UniqueConstraint("user_id", name=op.f("uq_wallets_user_id")),
    )
    op.create_index(op.f("ix_wallets_user_id"), "wallets", ["user_id"])

    # --- transactions ---
    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wallet_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), server_default="completed", nullable=False),
        sa.Column("provider", sa.String(30), nullable=True),
        sa.Column("provider_reference", sa.String(100), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"], ondelete="CASCADE", name=op.f("fk_transactions_wallet_id_wallets")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_transactions_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        sa.UniqueConstraint("reference", name=op.f("uq_transactions_reference")),
    )
    op.create_index(op.f("ix_transactions_type"), "transactions", ["type"])
    op.create_index(op.f("ix_transactions_user_id"), "transactions", ["user_id"])
    op.create_index(op.f("ix_transactions_reference"), "transactions", ["reference"])
    op.create_index(op.f("ix_transactions_created_at"), "transactions", ["created_at"])

    # --- withdrawals ---
    op.create_table(
        "withdrawals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("phone", sa.String(17), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("provider", sa.String(30), server_default="mpesa", nullable=True),
        sa.Column("provider_reference", sa.String(100), nullable=True),
        sa.Column("admin_note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_withdrawals_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_withdrawals")),
    )
    op.create_index(op.f("ix_withdrawals_user_id"), "withdrawals", ["user_id"])
    op.create_index(op.f("ix_withdrawals_status"), "withdrawals", ["status"])
    op.create_index(op.f("ix_withdrawals_created_at"), "withdrawals", ["created_at"])

    # --- referrals ---
    op.create_table(
        "referrals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("referrer_id", sa.Uuid(), nullable=False),
        sa.Column("referred_id", sa.Uuid(), nullable=True),
        sa.Column("referral_code", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("bonus_amount", sa.Numeric(12, 2), server_default="50.00", nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["referrer_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_referrals_referrer_id_users")),
        sa.ForeignKeyConstraint(["referred_id"], ["users.id"], ondelete="SET NULL", name=op.f("fk_referrals_referred_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_referrals")),
        sa.UniqueConstraint("referral_code", name=op.f("uq_referrals_referral_code")),
    )
    op.create_index(op.f("ix_referrals_referrer_id"), "referrals", ["referrer_id"])
    op.create_index(op.f("ix_referrals_referred_id"), "referrals", ["referred_id"])
    op.create_index(op.f("ix_referrals_referral_code"), "referrals", ["referral_code"])
    op.create_index(op.f("ix_referrals_status"), "referrals", ["status"])
    op.create_index(op.f("ix_referrals_created_at"), "referrals", ["created_at"])

    # --- referral_clicks ---
    op.create_table(
        "referral_clicks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("referral_code", sa.String(20), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_referral_clicks")),
    )
    op.create_index(op.f("ix_referral_clicks_referral_code"), "referral_clicks", ["referral_code"])
    op.create_index(op.f("ix_referral_clicks_created_at"), "referral_clicks", ["created_at"])

    # --- tasks ---
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reward_credits", sa.Integer(), server_default="10", nullable=False),
        sa.Column("content_url", sa.String(500), nullable=True),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("options", JSON, nullable=True),
        sa.Column("correct_answer", sa.String(200), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_type"), "tasks", ["type"])
    op.create_index(op.f("ix_tasks_is_active"), "tasks", ["is_active"])

    # --- task_completions ---
    op.create_table(
        "task_completions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("credits_earned", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_task_completions_user_id_users")),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE", name=op.f("fk_task_completions_task_id_tasks")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_completions")),
        sa.UniqueConstraint("user_id", "task_id", name=op.f("uq_task_completions_user_id_task_id")),
    )
    op.create_index(op.f("ix_task_completions_user_id"), "task_completions", ["user_id"])
    op.create_index(op.f("ix_task_completions_task_id"), "task_completions", ["task_id"])

    # --- credit_balances ---
    op.create_table(
        "credit_balances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("balance", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_earned", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_credit_balances_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_balances")),
        sa.UniqueConstraint("user_id", name=op.f("uq_credit_balances_user_id")),
    )
    op.create_index(op.f("ix_credit_balances_user_id"), "credit_balances", ["user_id"])

    # --- credit_transactions ---
    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name=op.f("fk_credit_transactions_user_id_users")),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL", name=op.f("fk_credit_transactions_task_id_tasks")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_transactions")),
    )
    op.create_index(op.f("ix_credit_transactions_user_id"), "credit_transactions", ["user_id"])
    op.create_index(op.f("ix_credit_transactions_source"), "credit_transactions", ["source"])
    op.create_index(op.f("ix_credit_transactions_created_at"), "credit_transactions", ["created_at"])


def downgrade() -> None:
    op.drop_table("credit_transactions")
    op.drop_table("credit_balances")
    op.drop_table("task_completions")
    op.drop_table("tasks")
    op.drop_table("referral_clicks")
    op.drop_table("referrals")
    op.drop_table("withdrawals")
    op.drop_table("transactions")
    op.drop_table("wallets")
    op.drop_index(op.f("ix_users_referral_code"), table_name="users")
    op.drop_column("users", "referral_code")
    op.drop_column("users", "is_admin")