"""
Message schemas for chat system with optional metadata support.

Metadata fields support future analysis and UI rendering:
- sources: References or sources used in the response
- confidence_score: Confidence level (0-1) of the response
- model_version: Version of the model that generated the response
- processing_time: Time taken to generate the response
- tokens_used: Number of tokens used in generation
- custom_metadata: Flexible field for any additional analysis data
"""

from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class AIMessageMetadata(BaseModel):
    """Optional metadata attached to AI-generated messages.
    
    All fields are optional to maintain backward compatibility
    and flexibility for different use cases.
    """
    sources: Optional[list[str]] = Field(
        default=None,
        description="List of sources or references used in the response"
    )
    confidence_score: Optional[float] = Field(
        default=None,
        description="Confidence level of the response (0.0-1.0)"
    )
    model_version: Optional[str] = Field(
        default=None,
        description="Version identifier of the AI model used"
    )
    processing_time_ms: Optional[int] = Field(
        default=None,
        description="Time taken to generate response in milliseconds"
    )
    tokens_used: Optional[int] = Field(
        default=None,
        description="Total tokens consumed in the API request"
    )
    input_tokens: Optional[int] = Field(
        default=None,
        description="Tokens used in the input/prompt"
    )
    output_tokens: Optional[int] = Field(
        default=None,
        description="Tokens generated in the response"
    )
    custom_metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Flexible field for any additional metadata or analysis data"
    )


class MessageBase(BaseModel):
    """Base fields for any message."""
    conversation_id: str
    role: str  # "user" or "assistant"
    content: str | list[str]
    created_at: datetime


class UserMessage(MessageBase):
    """A user message in the conversation."""
    user_id: str
    user_email: str
    source: str = "web"  # source of the message


class AIMessage(MessageBase):
    """An AI-generated message with optional metadata."""
    user_id: str
    user_email: str
    source: str = "ai"
    metadata: Optional[AIMessageMetadata] = Field(
        default=None,
        description="Optional metadata about the AI response"
    )


class ConversationMessage(BaseModel):
    """A message in conversation history (flexible shape from MongoDB)."""
    conversation_id: str
    role: str
    content: str | list[str]
    created_at: datetime
    metadata: Optional[AIMessageMetadata] = None
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    source: Optional[str] = None


class ConversationHistory(BaseModel):
    """Full conversation history with optional metadata."""
    conversation_id: str
    messages: list[ConversationMessage]
