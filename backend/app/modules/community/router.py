from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.modules.community.models import ChatMessage, ForexLesson
from app.modules.users.models import User

router = APIRouter(tags=["Community"])


class MessageCreate(BaseModel):
    recipient_id: UUID
    message: str = Field(min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sender_id: UUID
    recipient_id: UUID
    message: str
    created_at: datetime


class LessonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    summary: str
    content_url: str | None
    level: str


@router.get("/language-chat/partners")
def list_chat_partners(
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[dict]:
    query = select(User).where(User.id != user.id)
    if user.country_code:
        query = query.where(User.country_code.is_not(None), User.country_code != user.country_code)
    peers = db.scalars(query.order_by(User.name).limit(limit)).all()
    return [{"id": peer.id, "name": peer.name, "country_code": peer.country_code} for peer in peers]


@router.post("/language-chat/messages", response_model=MessageResponse, status_code=201)
def send_message(
    payload: MessageCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ChatMessage:
    recipient = db.get(User, payload.recipient_id)
    if recipient is None or recipient.id == user.id:
        raise HTTPException(status_code=404, detail="Chat partner not found.")
    message = ChatMessage(
        sender_id=user.id, recipient_id=recipient.id, message=payload.message.strip()
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.get("/language-chat/messages", response_model=list[MessageResponse])
def list_messages(
    with_user: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[ChatMessage]:
    return db.scalars(
        select(ChatMessage).where(
            or_(
                (ChatMessage.sender_id == user.id) & (ChatMessage.recipient_id == with_user),
                (ChatMessage.sender_id == with_user) & (ChatMessage.recipient_id == user.id),
            )
        ).order_by(ChatMessage.created_at.desc()).limit(limit)
    ).all()[::-1]


@router.get("/forex-classes", response_model=list[LessonResponse])
def list_forex_lessons(db: Session = Depends(get_db)) -> list[ForexLesson]:
    return db.scalars(
        select(ForexLesson).where(ForexLesson.is_active.is_(True)).order_by(ForexLesson.created_at)
    ).all()
