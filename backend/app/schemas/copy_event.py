# backend/app/schemas/copy_event.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CopyEventCreate(BaseModel):
    quiz_id: Optional[str] = None
    question_id: Optional[str] = None
    conversation_id: Optional[str] = None
    copied_text: str = Field(min_length=1, max_length=2000)


class CopyEventPublic(BaseModel):
    id: str
    user_id: str
    user_email: str
    quiz_id: Optional[str] = None
    question_id: Optional[str] = None
    conversation_id: Optional[str] = None
    copied_text: str
    created_at: datetime
