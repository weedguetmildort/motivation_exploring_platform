from pydantic import BaseModel, EmailStr, Field
from typing import Optional

from enum import Enum

class SurveyStage(str, Enum):
    pre_base = "pre_quiz"
    post_base = "post_base"
    post_variant = "post_variant"

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
    survey_pre_base_completed: bool = False
    quiz_base_completed: bool = False
    survey_post_base_completed: bool = False
    quiz_variant_completed: bool = False
    survey_post_variant_completed: bool = False
    survey_stage: SurveyStage = SurveyStage.pre_base

class UserDBDoc(BaseModel):
    """Shape as stored in Mongo."""
    _id: str
    email: EmailStr
    password_hash: str
    is_admin: bool = False
    demographics_completed: bool = False
    survey_pre_base_completed: bool = False
    quiz_base_completed: bool = False
    survey_post_base_completed: bool = False
    quiz_variant_completed: bool = False
    survey_post_variant_completed: bool = False
    survey_stage: SurveyStage = SurveyStage.pre_base
