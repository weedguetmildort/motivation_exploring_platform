# backend/app/schemas/study.py
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


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
    # Every variant the code currently declares, so the admin UI can render the
    # full list even if the stored order is stale.
    known_variants: List[str] = Field(default_factory=list)
    variant_labels: dict[str, str] = Field(default_factory=dict)
    # Worked example of the orders participants will actually receive.
    preview: List[List[str]] = Field(default_factory=list)


# Admin payload for changing the flow. All fields optional - partial update.
class StudyConfigUpdate(BaseModel):
    mode: Optional[Literal["all_variants", "single_variant"]] = None
    variant_order: Optional[List[str]] = None
    counterbalance: Optional[bool] = None
