# backend/app/schemas/link_click.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LinkClickCreate(BaseModel):
    quiz_id: Optional[str] = None
    question_id: Optional[str] = None
    conversation_id: Optional[str] = None
    url: str = Field(min_length=1)


class LinkClickPublic(BaseModel):
    id: str
    user_id: str
    user_email: str
    quiz_id: Optional[str] = None
    question_id: Optional[str] = None
    conversation_id: Optional[str] = None
    url: str
    clicked_at: datetime
