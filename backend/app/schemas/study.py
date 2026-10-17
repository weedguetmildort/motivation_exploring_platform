# backend/app/schemas/study.py
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SurveyStageSettings(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True


# One stop in the participant flow, as exposed to the client.
class StepPublic(BaseModel):
    id: str                       # e.g. "quiz:base", "survey:post_links"
    kind: Literal["quiz", "survey"]
    key: str                      # quiz_id for quizzes, response stage for surveys
    label: str
    route: str                    # frontend path for this step
    variant: Optional[str] = None
    completed: bool = False


# Returned by GET /study/next - the single authority the frontend uses to decide
# where a participant goes. Replaces the routing ladders that used to be
# duplicated across the quiz page, the survey page, and both backend services.
class NextStepResponse(BaseModel):
    next_step: Optional[StepPublic] = None
    next_route: str               # where to send the user right now
    completed_count: int = 0
    total_steps: int = 0
    finished: bool = False


# Returned by GET /study/flow - the participant's whole assigned journey, used
# for progress display ("Step 3 of 9").
class StudyFlowResponse(BaseModel):
    steps: List[StepPublic]
    variant_sequence: List[str] = Field(default_factory=list)
    current_step_id: Optional[str] = None
    completed_count: int = 0
    total_steps: int = 0
    finished: bool = False
    study_flow_version: int = 1
    mode: str = "all_variants"


# Admin view of the active flow configuration.
class StudyConfigPublic(BaseModel):
    mode: Literal["all_variants", "single_variant"]
    variant_order: List[str]
    counterbalance: bool
    version: int
    questions_per_quiz: int = 5
    wrong_ai_count: int = 3
    wrong_ai_rate: Optional[float] = None
    requires_study1_completion: bool = True
    requires_study2_approval: bool = True
    study_access_mode: str = "sequential_approval"
    study_id: Optional[str] = None
    survey_stages: dict[str, SurveyStageSettings] = Field(default_factory=dict)
    # Every variant the code currently declares, so the admin UI can render the
    # full list even if the stored order is stale.
    known_variants: List[str] = Field(default_factory=list)
    variant_labels: dict[str, str] = Field(default_factory=dict)
    # Worked example of the orders participants will actually receive.
    preview: List[List[str]] = Field(default_factory=list)

    # ── Per-quiz question sets ───────────────────────────────────────────────
    # Giving each quiz its own set is what keeps a participant's quizzes
    # disjoint. "preset" uses quiz_set_map verbatim; "random" shuffles the sets
    # across each participant's quizzes at signup. "balanced_random" randomizes
    # complete blocks of set rotations separately for each quiz order.
    quiz_set_mode: Literal["preset", "random", "balanced_random"] = "balanced_random"
    quiz_set_map: dict[str, str] = Field(default_factory=dict)
    # The set letters and the quizzes the code declares, so the admin UI renders
    # selects without hard-coding either.
    known_sets: List[str] = Field(default_factory=list)
    known_quiz_ids: List[str] = Field(default_factory=list)
    quiz_labels: dict[str, str] = Field(default_factory=dict)


# Admin payload for changing the flow. All fields optional - partial update.
class StudyConfigUpdate(BaseModel):
    survey_stages: Optional[dict[str, SurveyStageSettings]] = None
    questions_per_quiz: Optional[int] = Field(None, ge=1, le=100)
    wrong_ai_count: Optional[int] = Field(None, ge=0, le=100)
    wrong_ai_rate: Optional[float] = Field(None, ge=0, le=1)
    # Accepted from older clients, but access is controlled by STUDY_ACCESS_MODE.
    requires_study1_completion: Optional[bool] = Field(None, deprecated=True)
    mode: Optional[Literal["all_variants", "single_variant"]] = None
    variant_order: Optional[List[str]] = None
    counterbalance: Optional[bool] = None
    quiz_set_mode: Optional[Literal["preset", "random", "balanced_random"]] = None
    # quiz_id -> set letter. Omit a quiz to leave it drawing from the whole pool.
    quiz_set_map: Optional[dict[str, str]] = None
