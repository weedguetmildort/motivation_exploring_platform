# backend/app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# Tracks where the user is in the research study flow.
# Stages progress linearly: pre_quiz → post_base → post_variant → complete.
class SurveyStage(str, Enum):
    pre_base = "pre_quiz"
    post_base = "post_base"
    post_variant = "post_variant"
    complete = "complete"


# The study variant (chatbot type) assigned to the user at registration.
# Determines which chat endpoint and quiz the user sees.
class AssignedVar(str, Enum):
    followup = "followup"   # chatbot generates follow-up questions after each answer
    double = "double"       # two-agent chatbot (Agent A answers, Agent B checks)
    links = "links"         # chatbot response includes cited source links


# Internal representation of a user as stored in MongoDB.
# Never returned to the client directly — use UserPublic for API responses.
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


# Payload sent by the client when registering a new account.
class UserCreate(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=6)
    consent: bool


# Safe user representation returned to the client.
# Omits password_hash and exposes study-progress flags used to gate pages.
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


# Full document shape as stored in MongoDB, including all study-progress flags.
# Used internally when reading from the users collection.
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
