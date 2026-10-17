# backend/app/schemas/allowlist.py
from pydantic import BaseModel, Field
from datetime import datetime


class AllowlistCreate(BaseModel):
    domain: str = Field(min_length=1)


class AllowlistPublic(BaseModel):
    id: str
    domain: str
    added_by: str
    added_at: datetime
