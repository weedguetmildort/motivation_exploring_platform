# backend/app/schemas/survey.py
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Literal, Any, Dict

# The survey stage this item belongs to (e.g. "pre_quiz", "post_base", "post_variant").
SurveyStage = str  # keep flexible for now

# Supported question types: Likert scale or single-choice select.
SurveyItemType = Literal["likert", "single_select"]


# A single selectable option for single_select survey items.
class SurveyOption(BaseModel):
    id: str
    label: str


# Defines the numeric range and optional endpoint labels for a Likert scale item.
class SurveyScale(BaseModel):
    min: int = 1
    max: int = 5
    anchors: Optional[List[str]] = None  # e.g. ["Strongly disagree", "Strongly agree"]


# Shared fields and validation logic for all survey question types.
# The validator enforces that likert items have a scale and no options,
# and that single_select items have at least two non-empty options.
class SurveyItemBase(BaseModel):
    stage: SurveyStage
    prompt: str = Field(min_length=1)
    type: SurveyItemType = "likert"
    required: bool = True
    order: int = 0              # controls display order within a stage
    active: bool = True         # inactive items are hidden from participants

    category: Optional[str] = None      # optional grouping label for analysis
    reverse_scored: bool = False        # if True, score is inverted during analysis
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

# Payload sent by an admin when creating a new survey item. Inherits all SurveyItemBase fields.
class SurveyItemCreate(SurveyItemBase):
    pass


# Payload sent by an admin when partially updating a survey item.
# All fields are optional so only changed fields need to be provided.
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

# Survey item data returned to the client, including the database-assigned id.
class SurveyItemPublic(SurveyItemBase):
    id: str


# A single answer submitted by the user for one survey item.
# value type varies by item type: int for likert, str for single_select.
class SurveyAnswerIn(BaseModel):
    item_id: str
    value: Any  # can be int (likert), str (text), list[str] (multi_select)


# Full survey submission payload — all answers for a stage in one request.
class SurveySubmitRequest(BaseModel):
    answers: List[SurveyAnswerIn]


# A single answer as returned in the survey state, including timing fields for analysis.
class SurveyAnswerPublic(BaseModel):
    item_id: str
    value: Any
    shown_at: Optional[str] = None
    answered_at: Optional[str] = None


# Summary of the user's current survey attempt for a given stage.
class SurveyAttemptPublic(BaseModel):
    stage: SurveyStage
    status: str         # "in_progress" or "completed"
    answered_count: int
    total_items: int


# Full survey state returned to the client for a given stage.
# Contains the attempt summary, all items to display, and the user's existing answers.
class SurveyStateResponse(BaseModel):
    attempt: SurveyAttemptPublic
    items: List[SurveyItemPublic]
    answers: List[SurveyAnswerPublic]
