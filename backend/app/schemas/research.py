"""Bounded, semantic browser telemetry. Identity and study context are server supplied."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Region = Literal["question", "answers", "submit", "chat", "chat_input", "suggestions", "reference", "agent_A", "agent_B", "other"]
EventType = Literal[
    "question_visible", "question_left", "activity_interval", "region_click", "scroll",
    "answer_selected", "answer_submit_clicked", "answer_submit_failed",
    "prompt_sent", "ai_first_token", "ai_response_completed", "ai_response_failed", "ai_response_cancelled",
    "ai_message_displayed", "suggestion_displayed", "suggestion_clicked",
    "reference_displayed", "reference_clicked", "visibility_changed",
]


class EventData(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    region: Region | None = None
    duration_ms: float | None = Field(default=None, ge=0, le=15000)
    visible_ms: float | None = Field(default=None, ge=0, le=15000)
    focused_ms: float | None = Field(default=None, ge=0, le=15000)
    active_ms: float | None = Field(default=None, ge=0, le=15000)
    pointer_ms: float | None = Field(default=None, ge=0, le=15000)
    unobserved_ms: float | None = Field(default=None, ge=0)
    pointer_type: str | None = Field(default=None, max_length=20)
    request_id: str | None = Field(default=None, max_length=100)
    item_id: str | None = Field(default=None, max_length=200)
    agent: Literal["default", "A", "B"] | None = None
    position: int | None = Field(default=None, ge=0, le=1000)
    text: str | None = Field(default=None, max_length=2000)
    url: str | None = Field(default=None, max_length=2048)
    choice_id: str | None = Field(default=None, max_length=100)
    trigger: Literal["manual", "followup_chip", "auto_question"] | None = None
    visible: bool | None = None
    viewport_width: int | None = Field(default=None, ge=0, le=20000)
    viewport_height: int | None = Field(default=None, ge=0, le=20000)


class ResearchEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    event_id: str = Field(min_length=1, max_length=100)
    event_type: EventType
    conversation_id: str = Field(min_length=1, max_length=100)
    question_id: str = Field(min_length=1, max_length=100)
    page_id: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=0)
    occurred_at: datetime
    elapsed_ms: float = Field(ge=0)
    data: EventData = Field(default_factory=EventData)


class ResearchEventBatch(BaseModel):
    events: list[ResearchEvent] = Field(min_length=1, max_length=50)
