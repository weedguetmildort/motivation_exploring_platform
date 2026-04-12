# backend/app/schemas/knowledge_link.py
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional
from datetime import datetime

class KnowledgeLinkBase(BaseModel):
    title: str = Field(min_length=1)
    url: HttpUrl
    tags: List[str] = Field(default_factory=list)
    description: str = Field(min_length=1)
    active: bool = True

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
    active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class KnowledgeLinkDBDoc(BaseModel):
    _id: str
    title: str
    url: str
    tags: List[str] = Field(default_factory=list)
    description: str
    active: bool = True
    created_at: datetime
    updated_at: datetime