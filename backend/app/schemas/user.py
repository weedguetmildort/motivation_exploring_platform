# backend/app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


# Coarse label for where the user is in the study.
#
# NOTE: this is now a DERIVED field, recomputed from step_order/completed_steps
# by services/study_flow.derive_legacy_flags. Routing no longer reads it - it is
# kept accurate so existing Mongo queries, exports and analytics still work.
class SurveyStage(str, Enum):
    pre_base = "pre_quiz"
    post_base = "post_base"
    post_variant = "post_variant"
    complete = "complete"


# The study variants (chatbot types). Every participant now works through ALL
# of these, in a per-participant counterbalanced order; assigned_var records
# whichever one they saw first.
#
# Adding or removing a member here is all that is needed to add or remove a
# variant: the step registry, the assembled flow, and the round-robin rotation
# in services/study_flow.py all derive from this enum. A new variant also needs
# its chat endpoint in api/chat.py and a label in study_flow.VARIANT_LABELS.
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

    # --- study flow (authoritative) ---
    # The participant's whole assigned journey, snapshotted at signup, and the
    # steps of it they have finished. Routing reads these two fields only.
    step_order: List[str] = Field(default_factory=list)
    completed_steps: List[str] = Field(default_factory=list)
    variant_sequence: List[str] = Field(default_factory=list)
    study_flow_version: int = 1

    # --- derived legacy flags (read-only mirrors, not used for routing) ---
    survey_pre_base_completed: bool = False
    quiz_base_completed: bool = False
    survey_post_base_completed: bool = False
    quiz_variant_completed: bool = False        # True once ALL variant quizzes are done
    survey_post_variant_completed: bool = False # True once ALL post-variant surveys are done
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

    step_order: List[str] = Field(default_factory=list)
    completed_steps: List[str] = Field(default_factory=list)
    variant_sequence: List[str] = Field(default_factory=list)
    study_flow_version: int = 1

    survey_pre_base_completed: bool = False
    quiz_base_completed: bool = False
    survey_post_base_completed: bool = False
    quiz_variant_completed: bool = False
    survey_post_variant_completed: bool = False
    survey_stage: SurveyStage = SurveyStage.pre_base
