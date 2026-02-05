# backend/app/schemas/survey.py
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Literal, Any, Dict

SurveyStage = str  # keep flexible for now

SurveyItemType = Literal["likert", "single_select"]

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

    @model_validator(mode="before")
    @classmethod
    def _validate_item_by_type(cls, data):
        # Pydantic v2: "before" receives raw input (usually dict)
        if not isinstance(data, dict):
            return data

        t = data.get("type", "likert")
        scale = data.get("scale")
        options = data.get("options")

        if t == "likert":
            # ensure scale exists (default 1–5)
            if scale is None:
                data["scale"] = {
                    "min": 1,
                    "max": 5,
                    "anchors": ["Strongly disagree", "Strongly agree"],
                }
            # likert should not carry options
            data["options"] = None

        elif t == "single_select":
            # single_select must have options
            if not options or len(options) < 2:
                raise ValueError("single_select requires at least 2 options")

            # normalize option labels (strip whitespace), accept dict or object-like
            normalized = []
            for opt in options:
                opt_id = (opt.get("id") if isinstance(opt, dict) else getattr(opt, "id", None))
                opt_label = (opt.get("label") if isinstance(opt, dict) else getattr(opt, "label", ""))

                label = (opt_label or "").strip()
                if not label:
                    continue

                normalized.append({"id": opt_id, "label": label})

            if len(normalized) < 2:
                raise ValueError("single_select requires at least 2 non-empty option labels")

            data["options"] = normalized
            # single_select should not carry a likert scale
            data["scale"] = None

        return data

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

    @model_validator(mode="before")
    @classmethod
    def _normalize_patch(cls, data):
        # Pydantic v2: "before" receives raw input (usually dict)
        if not isinstance(data, dict):
            return data

        # If options included, strip empty labels
        opts = data.get("options")
        if opts is not None:
            normalized = []
            for opt in opts:
                # opt might be dict or SurveyOption-like
                opt_id = (opt.get("id") if isinstance(opt, dict) else getattr(opt, "id", None))
                opt_label = (opt.get("label") if isinstance(opt, dict) else getattr(opt, "label", ""))

                label = (opt_label or "").strip()
                if not label:
                    continue

                normalized.append({"id": opt_id, "label": label})
            data["options"] = normalized

        # If type is explicitly set, prevent obvious mismatches
        t = data.get("type")
        if t == "likert":
            data["options"] = None
            # If admin didn't provide scale in patch, service layer can keep existing scale.
        elif t == "single_select":
            data["scale"] = None
            # options validation should be finalized after merge in service layer.

        return data

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
