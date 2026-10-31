from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    title: str
    description: str | None
    reward_credits: int
    content_url: str | None
    question: str | None
    options: list[str] | None
    completed: bool = False


class CompleteTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str | None = Field(None, description="Answer for trivia tasks")


class TaskCompletionResponse(BaseModel):
    task_id: UUID
    credits_earned: int
    total_credits: int
    message: str