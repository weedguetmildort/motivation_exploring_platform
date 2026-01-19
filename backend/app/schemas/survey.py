# backend/app/schemas/survey.py
from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Any, Dict

SurveyStage = str  # keep flexible for now

SurveyItemType = Literal["likert", "text", "single_select", "multi_select"]

class SurveyOption(BaseModel):
    id: str
    label: str

class SurveyScale(BaseModel):
    min: int = 1
    max: int = 5
    anchors: Optional[List[str]] = None  # e.g. ["Strongly disagree", "Strongly agree"]

class SurveyItemBase(BaseModel):
    stage: SurveyStage
    prompt: str = Field(min_length=1)
    type: SurveyItemType = "likert"
    required: bool = True
    order: int = 0
    active: bool = True

    category: Optional[str] = None
    reverse_scored: bool = False
    scale: Optional[SurveyScale] = None
    options: Optional[List[SurveyOption]] = None  # for select types

class SurveyItemCreate(SurveyItemBase):
    pass

class SurveyItemUpdate(BaseModel):
    prompt: Optional[str] = None
    type: Optional[SurveyItemType] = None
    required: Optional[bool] = None
    order: Optional[int] = None
    active: Optional[bool] = None
    category: Optional[str] = None
    reverse_scored: Optional[bool] = None
    scale: Optional[SurveyScale] = None
    options: Optional[List[SurveyOption]] = None

class SurveyItemPublic(SurveyItemBase):
    id: str

class SurveyAnswerIn(BaseModel):
    item_id: str
    value: Any  # can be int (likert), str (text), list[str] (multi_select)

class SurveySubmitRequest(BaseModel):
    answers: List[SurveyAnswerIn]

class SurveyAnswerPublic(BaseModel):
    item_id: str
    value: Any
    shown_at: Optional[str] = None
    answered_at: Optional[str] = None

class SurveyAttemptPublic(BaseModel):
    stage: SurveyStage
    status: str
    answered_count: int
    total_items: int

class SurveyStateResponse(BaseModel):
    attempt: SurveyAttemptPublic
    items: List[SurveyItemPublic]
    answers: List[SurveyAnswerPublic]
