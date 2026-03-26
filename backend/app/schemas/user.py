# backend/app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class SurveyStage(str, Enum):
    pre_base = "pre_quiz"
    post_base = "post_base"
    post_variant = "post_variant"
    complete = "complete"

class AssignedVar(str, Enum):
    followup = "followup"
    double = "double"
    links = "links"

class UserInDB(BaseModel):
    id: str
    email: EmailStr
    password_hash: str
    first_name: str
    last_name: str
    consent: bool = True
    consent_given_at: datetime
    assigned_var: AssignedVar = AssignedVar.followup
    is_admin: bool = False

class UserCreate(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=6)
    consent: bool

class UserPublic(BaseModel):
    id: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    consent: Optional[bool] = None
    consent_given_at: Optional[datetime] = None
    assigned_var: AssignedVar = AssignedVar.followup
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
    first_name: str
    last_name: str
    consent: bool = True
    consent_given_at: datetime
    assigned_var: AssignedVar = AssignedVar.followup
    is_admin: bool = False
    demographics_completed: bool = False
    survey_pre_base_completed: bool = False
    quiz_base_completed: bool = False
    survey_post_base_completed: bool = False
    quiz_variant_completed: bool = False
    survey_post_variant_completed: bool = False
    survey_stage: SurveyStage = SurveyStage.pre_base