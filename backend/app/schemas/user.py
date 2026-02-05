from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class UserInDB(BaseModel):
    id: str
    email: EmailStr
    password_hash: str
    is_admin: bool = False

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)

class UserPublic(BaseModel):
    id: str
    email: EmailStr
    is_admin: bool = False
    demographics_completed: bool = False
    quiz_pre_survey_completed: bool = False

class UserDBDoc(BaseModel):
    """Shape as stored in Mongo."""
    _id: str
    email: EmailStr
    password_hash: str
    is_admin: bool = False
    demographics_completed: bool = False
    quiz_pre_survey_completed: bool = False
