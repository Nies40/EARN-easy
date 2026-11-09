"""Add earning submissions, language chat, and forex classes.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("country_code", sa.String(2), nullable=True))
    op.add_column("task_completions", sa.Column("submission", sa.Text(), nullable=True))
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
    )
    op.create_index(op.f("ix_chat_messages_sender_id"), "chat_messages", ["sender_id"])
    op.create_index(op.f("ix_chat_messages_recipient_id"), "chat_messages", ["recipient_id"])
    op.create_table(
        "forex_lessons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content_url", sa.String(500), nullable=True),
        sa.Column("level", sa.String(30), server_default="beginner", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forex_lessons")),
    )
    op.create_index(op.f("ix_forex_lessons_is_active"), "forex_lessons", ["is_active"])
    lessons = sa.table(
        "forex_lessons",
        sa.column("id", sa.Uuid()),
        sa.column("title", sa.String()),
        sa.column("summary", sa.Text()),
        sa.column("content_url", sa.String()),
        sa.column("level", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        lessons,
        [
            {
                "id": "00000000-0000-4000-8000-000000000001",
                "title": "Forex basics and currency pairs",
                "summary": (
                    "Learn how currency pairs are quoted, what bid and ask mean, and how "
                    "pips and lot sizes work. This lesson is educational and does not "
                    "promise earnings."
                ),
                "content_url": None,
                "level": "beginner",
                "is_active": True,
            },
            {
                "id": "00000000-0000-4000-8000-000000000002",
                "title": "Risk management before trading",
                "summary": (
                    "Understand position sizing, stop losses, leverage risk, and why you "
                    "should never trade money you cannot afford to lose. Practise with a "
                    "demo account before considering live markets."
                ),
                "content_url": None,
                "level": "beginner",
                "is_active": True,
            },
            {
                "id": "00000000-0000-4000-8000-000000000003",
                "title": "Reading a basic price chart",
                "summary": (
                    "Explore candlesticks, timeframes, support and resistance, and the "
                    "limits of technical analysis. Past price movement does not predict "
                    "future results."
                ),
                "content_url": None,
                "level": "beginner",
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("forex_lessons")
    op.drop_table("chat_messages")
    op.drop_column("task_completions", "submission")
    op.drop_column("users", "country_code")
