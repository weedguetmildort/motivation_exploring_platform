# backend/app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal, List
from datetime import datetime
from enum import Enum

from .question import SetId  # "a" | "b" | "c" | "d" — question set labels


# Coarse label for where the user is in the study.
#
# NOTE: this is now a DERIVED field, recomputed from step_order/completed_steps
# by services/study_flow.derive_legacy_flags. Routing no longer reads it — it is
# kept accurate so existing Mongo queries, exports and the participants panel
# keep working.
class SurveyStage(str, Enum):
    pre_base = "pre_quiz"
    post_base = "post_base"
    post_variant = "post_variant"
    complete = "complete"


# The study variants (chatbot types). Every participant now works through ALL of
# these, in a per-participant counterbalanced order; assigned_var records
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

    # ── Study flow (authoritative) ───────────────────────────────────────────
    # The participant's whole assigned journey, snapshotted at signup, and the
    # steps of it they have finished. Routing reads these two fields only.
    step_order: List[str] = Field(default_factory=list)
    completed_steps: List[str] = Field(default_factory=list)
    variant_sequence: List[str] = Field(default_factory=list)
    study_flow_version: int = 1

    # ── Derived legacy mirrors (not used for routing) ────────────────────────
    survey_pre_base_completed: bool = False
    quiz_base_completed: bool = False
    survey_post_base_completed: bool = False
    quiz_variant_completed: bool = False        # True once ALL variant quizzes are done
    survey_post_variant_completed: bool = False # True once ALL post-variant surveys are done
    survey_stage: SurveyStage = SurveyStage.pre_base
    # Which question set(s) this participant draws from in the quiz. None = no
    # restriction (all questions). See Phase 11 — quiz set restriction.
    quiz_sets: Optional[List[SetId]] = None
    # Admin-granted access to the follow-up study (Phase 13). The dashboard card
    # additionally requires the main study to be complete.
    followup_study_granted: bool = False


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
    followup_study_granted: bool = False
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


# Admin request to grant/revoke a participant's follow-up study access (Phase 13).
class FollowupStudyUpdate(BaseModel):
    granted: bool
