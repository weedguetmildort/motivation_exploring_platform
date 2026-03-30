from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from .message import AIMessageMetadata


# Sent by the client to any chat endpoint.
class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None  # omit to start a new conversation
    agents: list[str] = []             # e.g. ["agentA", "agentB"] for double-agent mode


# Returned by non-streaming chat endpoints (e.g. legacy or search-based).
class ChatResponse(BaseModel):
    reply: list[str]                          # one entry per agent response
    conversation_id: str
    metadata: Optional[list[AIMessageMetadata]] = None


# Returned by the follow-up endpoint; extends the base reply with generated follow-up questions.
class FollowupChatResponse(BaseModel):
    reply: list[str]
    conversation_id: str
    followup_questions: list[str]


# Standalone wrapper for a list of follow-up question strings.
class FollowupResponse(BaseModel):
    questions: list[str]


# A single message entry used in the lightweight user-facing history view.
# Content may be a plain string (user message) or a list of strings (multi-agent reply).
class UserMessageData(BaseModel):
    role: str               # "user" or "assistant"
    content: str | list[str]


# Returned by /chat/load_user_history — recent messages for the current user only.
class UserConversationHistoryResponse(BaseModel):
    conversation_id: str
    messages: list[UserMessageData]


# A single message entry in the full admin conversation history view.
# Includes timestamp, optional AI metadata, and the email of the user who sent it.
class ConversationMessageData(BaseModel):
    role: str               # "user" or "assistant"
    content: str | list[str]
    created_at: datetime
    metadata: Optional[AIMessageMetadata] = None  # populated for assistant messages
    user_email: Optional[str] = None


# Returned by /chat/get_history — full conversation history with timestamps and metadata.
class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    messages: list[ConversationMessageData]
