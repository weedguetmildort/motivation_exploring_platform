# backend/app/schemas/knowledge_link.py
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional
from datetime import datetime


class LinkStatus(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"


class KnowledgeLinkBase(BaseModel):
    title: str = Field(min_length=1)
    url: HttpUrl
    tags: List[str] = Field(default_factory=list)
    description: str = Field(min_length=1)


class KnowledgeLinkCreate(KnowledgeLinkBase):
    pass


class KnowledgeLinkUpdate(KnowledgeLinkBase):
    pass


class KnowledgeLinkPublic(BaseModel):
    id: str
    title: str
    url: HttpUrl
    tags: List[str] = Field(default_factory=list)
    description: str
    status: LinkStatus = LinkStatus.READY
    last_checked: Optional[datetime] = None
    last_http_code: Optional[int] = None
    last_error_type: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
