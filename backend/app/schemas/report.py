# backend/app/schemas/report.py
from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class ReportCategory(str, Enum):
    BUG = "bug"
    UNCLEAR_QUESTION = "unclear_question"
    WRONG_ANSWER = "wrong_answer"
    TECHNICAL = "technical"
    OTHER = "other"


class ReportStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class CommentPublic(BaseModel):
    id: str
    author_email: str
    is_admin: bool
    body: str
    created_at: datetime


class ReportCreate(BaseModel):
    category: ReportCategory
    description: str = Field(min_length=1)
    quiz_id: Optional[str] = None
    question_id: Optional[str] = None


class ReportPublic(BaseModel):
    id: str
    user_email: str
    quiz_id: Optional[str] = None
    question_id: Optional[str] = None
    category: ReportCategory
    description: str
    status: ReportStatus = ReportStatus.OPEN
    comments: List[CommentPublic] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)


class StatusUpdate(BaseModel):
    status: ReportStatus
