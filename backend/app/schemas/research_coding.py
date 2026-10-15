from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ConversationLabels(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_reasoning: Literal["not_observed", "specific_step", "worked_reasoning", "insufficient_evidence"]
    challenge_quality: Literal["not_observed", "generic_check", "specific_error", "insufficient_evidence"]
    misconception: Literal["not_observed", "arithmetic", "conceptual", "question_interpretation", "procedure", "multiple", "insufficient_evidence"]
    disagreement_handling: Literal["not_observed", "comparison", "own_check", "reconciliation_request", "insufficient_evidence"]
    ai_explanation_issue: Literal["not_observed", "unsupported_claim", "contradiction", "calculation_error", "insufficient_evidence"]
    ai_certainty: Literal["not_observed", "hedged", "assertive", "mixed", "insufficient_evidence"]
    ai_relevance: Literal["not_observed", "focused", "off_topic", "mixed", "insufficient_evidence"]
    reference_discussion: Literal["not_observed", "requests_source", "discusses_reference", "insufficient_evidence"]
    suggestion_quality: Literal["not_observed", "explanation_or_verification", "answer_seeking", "mixed", "insufficient_evidence"]


class CodingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: str = Field(max_length=50)
    turn_id: str = Field(max_length=200)
    quote: str = Field(min_length=1, max_length=2000)


class ConversationCoding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    labels: ConversationLabels
    evidence: list[CodingEvidence] = Field(default_factory=list, max_length=40)
    notes: str = Field(default="", max_length=4000)


class HumanCodingRequest(ConversationCoding):
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    independent_review: bool = False


class ModelCodingRequest(BaseModel):
    packet_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
