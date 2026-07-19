# backend/app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal, List
from datetime import datetime
from enum import Enum

from .question import SetId  # "a" | "b" | "c" | "d" — question set labels


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
    consent_text: Optional[str] = None
    consent_agreed_at: Optional[datetime] = None
    consent_declined_at: Optional[datetime] = None
    # Funnel telemetry: when the participant first reached the consent page
    # (viewed) and, if they left without agreeing/declining, when they did so
    # (abandoned — e.g. closed the tab). See app/api/auth.py consent endpoints.
    consent_viewed_at: Optional[datetime] = None
    consent_abandoned_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    assigned_var: AssignedVar = AssignedVar.followup
    is_admin: bool = False
    demographics_completed: bool = False
    survey_pre_base_completed: bool = False
    quiz_base_completed: bool = False
    survey_post_base_completed: bool = False
    quiz_variant_completed: bool = False
    survey_post_variant_completed: bool = False
    survey_stage: SurveyStage = SurveyStage.pre_base
    # Which question set(s) this participant draws from in the quiz. None = no
    # restriction (all questions). See Phase 11 — quiz set restriction.
    quiz_sets: Optional[List[SetId]] = None


# Admin-facing view of a participant — adds created_at, omits password_hash.
class ParticipantSummary(BaseModel):
    id: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    assigned_var: AssignedVar = AssignedVar.followup
    survey_stage: SurveyStage = SurveyStage.pre_base
    demographics_completed: bool = False
    survey_pre_base_completed: bool = False
    quiz_base_completed: bool = False
    survey_post_base_completed: bool = False
    quiz_variant_completed: bool = False
    survey_post_variant_completed: bool = False
    last_active_at: Optional[datetime] = None
    consent_declined_at: Optional[datetime] = None
    consent_viewed_at: Optional[datetime] = None
    consent_abandoned_at: Optional[datetime] = None
    quiz_sets: Optional[List[SetId]] = None
    created_at: Optional[datetime] = None


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


# What condition the next new participant will be assigned, and why.
# "override" = an admin pinned it (one-shot); "rotation" = normal round-robin.
class NextAssignment(BaseModel):
    next: AssignedVar
    source: Literal["override", "rotation"]


# Admin request to pin the next assignment. `null` clears the override and
# returns to round-robin rotation.
class NextAssignmentUpdate(BaseModel):
    variant: Optional[AssignedVar] = None


# The global default question set(s) stamped onto new sign-ups. `null`/empty =
# no restriction (participants draw from all questions).
class QuizDefaultSets(BaseModel):
    sets: Optional[List[SetId]] = None


# Admin request to override one participant's allowed question set(s). `null` =
# clear the restriction (draw from all questions).
class ParticipantSetsUpdate(BaseModel):
    quiz_sets: Optional[List[SetId]] = None
