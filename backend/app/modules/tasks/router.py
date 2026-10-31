from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.modules.tasks import service
from app.modules.tasks.schemas import (
    CompleteTaskRequest,
    TaskCompletionResponse,
    TaskResponse,
)
from app.modules.users.models import User

router = APIRouter(tags=["Tasks"])


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TaskResponse]:
    tasks = service.list_tasks(db, user.id)
    return [
        TaskResponse(
            id=t.id,
            type=t.type,
            title=t.title,
            description=t.description,
            reward_credits=t.reward_credits,
            content_url=t.content_url,
            question=t.question,
            options=t.options,
            completed=service.is_completed(db, user.id, t.id),
        )
        for t in tasks
    ]


@router.post("/tasks/{task_id}/complete", response_model=TaskCompletionResponse)
def complete_task(
    task_id: str,
    payload: CompleteTaskRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskCompletionResponse:
    try:
        result = service.complete_task(db, user.id, task_id, payload.answer)
    except ValueError as error:
        status = 409 if "already completed" in str(error) else 400
        raise HTTPException(status_code=status, detail=str(error)) from error
    return TaskCompletionResponse(**result)