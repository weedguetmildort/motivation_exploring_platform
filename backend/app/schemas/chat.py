from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from .message import AIMessageMetadata


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    agents: list[str] = []


class ChatResponse(BaseModel):
    reply: list[str]
    conversation_id: str
    metadata: Optional[list[AIMessageMetadata]] = None


class FollowupChatResponse(BaseModel):
    reply: list[str]
    conversation_id: str
    followup_questions: list[str]


class FollowupResponse(BaseModel):
    questions: list[str]


class UserMessageData(BaseModel):
    role: str
    content: str | list[str]


class UserConversationHistoryResponse(BaseModel):
    conversation_id: str
    messages: list[UserMessageData]


class ConversationMessageData(BaseModel):
    role: str
    content: str | list[str]
    created_at: datetime
    metadata: Optional[AIMessageMetadata] = None
    user_email: Optional[str] = None


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    messages: list[ConversationMessageData]
