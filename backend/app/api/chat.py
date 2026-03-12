import os
import re
import uuid
import time
from pydantic import BaseModel
from openai import OpenAI
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from typing import Optional
from ..schemas.user import UserPublic
from ..schemas.message import AIMessageMetadata
from .auth import get_current_user
from ..services.chat import get_last_exchange

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None

class ChatResponse(BaseModel):
    reply: list[str]
    conversation_id: str
    metadata: Optional[list[AIMessageMetadata]] = None  # Optional metadata for each reply


def _extract_metadata_from_response(resp, model_version: Optional[str] = None) -> AIMessageMetadata:
    """Extract metadata from OpenAI API response.
    
    Parameters:
    - resp: OpenAI ChatCompletion response object
    - model_version: Optional model version to include
    
    Returns:
    - AIMessageMetadata with populated fields
    """
    return AIMessageMetadata(
        model_version=model_version or getattr(resp, 'model', None),
        tokens_used=getattr(resp.usage, 'total_tokens', None) if resp.usage else None,
        input_tokens=getattr(resp.usage, 'prompt_tokens', None) if resp.usage else None,
        output_tokens=getattr(resp.usage, 'completion_tokens', None) if resp.usage else None,
        # Other fields can be set by additional processing or custom logic
    )

# Initialize OpenAI client with UF proxy settings (from env)
_UF_API_KEY = os.getenv("UF_OPENAI_API_KEY")
_UF_BASE_URL = os.getenv("UF_OPENAI_BASE_URL", "https://api.ai.it.ufl.edu")
_client = OpenAI(api_key=_UF_API_KEY, base_url=_UF_BASE_URL)


# Draft for new chatbot feature — registered before the catch-all {quiz_id} route
@router.post("/chat/double", response_model=ChatResponse)
async def double_chat(
    req: ChatRequest,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    if not _UF_API_KEY:
        raise HTTPException(status_code=500, detail="Backend missing UF_OPENAI_API_KEY")

    conv_id = req.conversation_id or str(uuid.uuid4())
    model_version = os.getenv("UF_OPENAI_API_MODEL")

    # Fetch history BEFORE inserting the new user message
    history = get_last_exchange(request.app.state.messages, conv_id)

    # Insert user message
    try:
        request.app.state.messages.insert_one({
            "conversation_id": conv_id,
            "role": "user",
            "user_id": user.id,
            "user_email": user.email,
            "content": req.message,
            "created_at": datetime.utcnow(),
            "source": "web",
        })
    except Exception:
        pass

    # Agent A: sees full prior conversation
    metadata_a = None
    try:
        system_instruction = (
            "You are a helpful assistant who generates clear and concise answers "
            "to help students answer some quiz questions."
        )
        messages_a = [
            {"role": "system", "content": system_instruction},
            *history,
            {"role": "user", "content": req.message},
        ]
        start_time = time.time()
        resp = _client.chat.completions.create(
            model=model_version,
            messages=messages_a,
        )
        processing_time_ms = int((time.time() - start_time) * 1000)
        reply = (resp.choices[0].message.content or "").strip()
        
        # Extract metadata from response
        metadata_a = _extract_metadata_from_response(resp, model_version)
        metadata_a.processing_time_ms = processing_time_ms
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream AI request failed")

    # Agent B: sees full prior conversation plus Agent A's new response
    metadata_b = None
    try:
        system_instruction_b = (
            "You are a helpful assistant who generates clear and concise answers "
            "to help students answer some quiz questions. "
            "Double check that the answers provided by [AGENT A] are correct, and if not, provide the correct answer."
        )
        messages_b = [
            {"role": "system", "content": system_instruction_b},
            *history,
            {"role": "user", "content": req.message},
            {"role": "assistant", "content": f"[AGENT A] {reply}"},
        ]
        start_time = time.time()
        resp = _client.chat.completions.create(
            model=model_version,
            messages=messages_b,
        )
        processing_time_ms = int((time.time() - start_time) * 1000)
        second_reply = (resp.choices[0].message.content or "").strip()
        
        # Extract metadata from response
        metadata_b = _extract_metadata_from_response(resp, model_version)
        metadata_b.processing_time_ms = processing_time_ms
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream AI request failed")

    # Insert both agent replies as a single assistant document with metadata
    try:
        request.app.state.messages.insert_one({
            "conversation_id": conv_id,
            "role": "assistant",
            "user_id": user.id,
            "user_email": user.email,
            "content": [reply, second_reply],
            "created_at": datetime.utcnow(),
            "source": "ai",
            "metadata": {
                "agents": [
                    metadata_a.model_dump(exclude_none=True) if metadata_a else {},
                    metadata_b.model_dump(exclude_none=True) if metadata_b else {},
                ],
            }
        })
    except Exception:
        pass

    return ChatResponse(
        reply=[reply, second_reply],
        conversation_id=conv_id,
        metadata=[metadata_a, metadata_b] if (metadata_a or metadata_b) else None,
    )


class FollowupRequest(BaseModel):
    last_ai_message: str

class FollowupResponse(BaseModel):
    questions: list[str]

@router.post("/chat/followup", response_model=FollowupResponse)
async def followup_chat(
    req: FollowupRequest,
    user: UserPublic = Depends(get_current_user),
):
    if not _UF_API_KEY:
        raise HTTPException(status_code=500, detail="Backend missing UF_OPENAI_API_KEY")

    system_prompt = (
        "You are a helpful assistant who generates short follow-up questions "
        "related ONLY to the explanation you just gave the student. "
        "Your follow-up questions MUST be: directly related to the explanation, "
        "concise (1 sentence, max 12 words), simple and beginner-friendly, "
        "NOT about homework, exams, studying, or general help. "
        "Return ONLY the 3 questions as a numbered list (1., 2., 3.)."
    )
    user_prompt = (
        f"Here is the last thing you told the student:\n\n{req.last_ai_message}"
        "\n\nGenerate exactly 3 possible follow-up questions the student might ask next."
    )

    try:
        resp = _client.chat.completions.create(
            model=os.getenv("UF_OPENAI_API_MODEL"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream AI request failed")

    questions: list[str] = []
    for line in raw.split("\n"):
        trimmed = line.strip()
        if not trimmed:
            continue
        m = re.match(r"^[0-9]+[.)\-:\s]+(.*)", trimmed)
        if m:
            text = m.group(1).strip()
            if text:
                questions.append(text)
    if not questions:
        questions = [raw]
    questions = questions[:3]

    return FollowupResponse(questions=questions)


@router.post("/chat/{quiz_id}", response_model=ChatResponse)
async def chat(
    quiz_id: str,
    req: ChatRequest,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    if not _UF_API_KEY:
        raise HTTPException(status_code=500, detail="Backend missing UF_OPENAI_API_KEY")

    conv_id = req.conversation_id or str(uuid.uuid4())
    model_version = os.getenv("UF_OPENAI_API_MODEL")

    # Fetch history BEFORE inserting the new user message
    history = get_last_exchange(request.app.state.messages, conv_id)

    # Insert user message
    try:
        request.app.state.messages.insert_one({
            "conversation_id": conv_id,
            "role": "user",
            "user_id": user.id,
            "user_email": user.email,
            "content": req.message,
            "created_at": datetime.utcnow(),
            "source": "web",
        })
    except Exception:
        pass

    metadata = None
    try:
        system_instruction = (
            "You are a helpful assistant who generates clear and concise answers "
            "to help students answer some quiz questions."
        )
        messages = [
            {"role": "system", "content": system_instruction},
            *history,
            {"role": "user", "content": req.message},
        ]
        start_time = time.time()
        resp = _client.chat.completions.create(
            model=model_version,
            messages=messages,
        )
        processing_time_ms = int((time.time() - start_time) * 1000)
        reply = (resp.choices[0].message.content or "").strip()
        
        # Extract metadata from response
        metadata = _extract_metadata_from_response(resp, model_version)
        metadata.processing_time_ms = processing_time_ms
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream AI request failed")

    # Insert assistant message with metadata
    try:
        request.app.state.messages.insert_one({
            "conversation_id": conv_id,
            "role": "assistant",
            "user_id": user.id,
            "user_email": user.email,
            "content": [reply],
            "created_at": datetime.utcnow(),
            "source": "ai",
            "metadata": metadata.model_dump(exclude_none=True) if metadata else None,
        })
    except Exception:
        pass

    return ChatResponse(
        reply=[reply],
        conversation_id=conv_id,
        metadata=[metadata] if metadata else None,
    )


# New endpoint: retrieve conversation history with metadata
class ConversationMessageData(BaseModel):
    """A single message in the conversation with optional metadata."""
    role: str
    content: str | list[str]
    created_at: datetime
    metadata: Optional[AIMessageMetadata] = None
    user_email: Optional[str] = None


class ConversationHistoryResponse(BaseModel):
    """Full conversation history with metadata."""
    conversation_id: str
    messages: list[ConversationMessageData]


@router.get("/chat/history/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    conversation_id: str,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    """Retrieve full conversation history including optional metadata.
    
    This endpoint returns all messages in a conversation with their metadata,
    useful for analysis, debugging, and UI rendering of message sources/confidence.
    """
    try:
        # Fetch all messages for this conversation
        docs = list(request.app.state.messages.find(
            {"conversation_id": conversation_id},
            sort=[("created_at", 1)],  # chronological order
        ))
        
        if not docs:
            # Return empty history if not found
            return ConversationHistoryResponse(
                conversation_id=conversation_id,
                messages=[]
            )
        
        # Check that the user owns this conversation (matches user_id in message)
        if docs and docs[0].get("user_id") != user.id:
            raise HTTPException(status_code=403, detail="Unauthorized access to conversation")
        
        messages = []
        for doc in docs:
            # Parse metadata if present
            metadata_dict = doc.get("metadata")
            metadata = None
            if metadata_dict:
                try:
                    # Handle nested metadata structure (e.g., for double_chat with agents)
                    if isinstance(metadata_dict, dict) and "agents" not in metadata_dict:
                        metadata = AIMessageMetadata(**metadata_dict)
                except Exception:
                    # If metadata parsing fails, skip it
                    pass
            
            messages.append(ConversationMessageData(
                role=doc.get("role", ""),
                content=doc.get("content", ""),
                created_at=doc.get("created_at", datetime.utcnow()),
                metadata=metadata,
                user_email=doc.get("user_email"),
            ))
        
        return ConversationHistoryResponse(
            conversation_id=conversation_id,
            messages=messages
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve conversation: {str(e)}")

