import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


class Task(Base):
    """A task the user can complete for credits: watch video, like photo, or answer trivia."""

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(20), index=True)  # video|photo_like|trivia
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    reward_credits: Mapped[int] = mapped_column(Integer, default=10)
    content_url: Mapped[str | None] = mapped_column(String(500))  # video/photo URL
    question: Mapped[str | None] = mapped_column(Text)  # trivia question
    options: Mapped[list | None] = mapped_column(JSON)  # trivia answer options
    correct_answer: Mapped[str | None] = mapped_column(String(200))  # trivia answer
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TaskCompletion(Base):
    """Record of a user completing a task. Unique per (user_id, task_id)."""

    __tablename__ = "task_completions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    credits_earned: Mapped[int] = mapped_column(Integer)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )