from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.credits import service as credits_service
from app.modules.tasks.models import Task, TaskCompletion


def list_tasks(db: Session, user_id: UUID) -> list[Task]:
    return (
        db.scalars(
            select(Task)
            .where(Task.is_active.is_(True))
            .order_by(Task.created_at.desc())
        )
        .all()
    )


def is_completed(db: Session, user_id: UUID, task_id: UUID) -> bool:
    return db.scalar(
        select(TaskCompletion.id)
        .where(
            TaskCompletion.user_id == user_id,
            TaskCompletion.task_id == task_id,
        )
        .limit(1)
    ) is not None


def complete_task(db: Session, user_id: UUID, task_id: UUID, answer: str | None = None) -> dict:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.is_active.is_(True)))
    if task is None:
        raise ValueError("Task not found.")

    if is_completed(db, user_id, task_id):
        raise ValueError("Task already completed.")

    # Validate trivia answer
    if task.type == "trivia" and task.correct_answer:
        if answer is None or answer.strip().lower() != task.correct_answer.strip().lower():
            raise ValueError("Incorrect answer. Try again.")

    try:
        completion = TaskCompletion(
            user_id=user_id,
            task_id=task_id,
            credits_earned=task.reward_credits,
        )
        db.add(completion)
        credits_service.earn_credits(
            db,
            user_id,
            task.reward_credits,
            "task",
            task_id=task_id,
            description=f"Completed: {task.title}",
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise ValueError("Task already completed.") from error

    balance = credits_service.get_or_create_balance(db, user_id)
    return {
        "task_id": str(task_id),
        "credits_earned": task.reward_credits,
        "total_credits": balance.balance,
        "message": f"Task completed! You earned {task.reward_credits} credits.",
    }