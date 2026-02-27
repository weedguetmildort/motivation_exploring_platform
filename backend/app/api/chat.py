import os
import uuid
from pydantic import BaseModel
from openai import OpenAI
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from ..schemas.user import UserPublic
from .auth import get_current_user
from ..services.chat import get_last_exchange

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None

class ChatResponse(BaseModel):
    reply: list[str]
    conversation_id: str

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
        resp = _client.chat.completions.create(
            model=os.getenv("UF_OPENAI_API_MODEL"),
            messages=messages_a,
        )
        reply = (resp.choices[0].message.content or "").strip()
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream AI request failed")

    # Agent B: sees full prior conversation plus Agent A's new response
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
        resp = _client.chat.completions.create(
            model=os.getenv("UF_OPENAI_API_MODEL"),
            messages=messages_b,
        )
        second_reply = (resp.choices[0].message.content or "").strip()
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream AI request failed")

    # Insert both agent replies as a single assistant document
    try:
        request.app.state.messages.insert_one({
            "conversation_id": conv_id,
            "role": "assistant",
            "user_id": user.id,
            "user_email": user.email,
            "content": [reply, second_reply],
            "created_at": datetime.utcnow(),
            "source": "ai",
        })
    except Exception:
        pass

    return ChatResponse(reply=[reply, second_reply], conversation_id=conv_id)


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
        resp = _client.chat.completions.create(
            model=os.getenv("UF_OPENAI_API_MODEL"),
            messages=messages,
        )
        reply = (resp.choices[0].message.content or "").strip()
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream AI request failed")

    # Insert assistant message
    try:
        request.app.state.messages.insert_one({
            "conversation_id": conv_id,
            "role": "assistant",
            "user_id": user.id,
            "user_email": user.email,
            "content": [reply],
            "created_at": datetime.utcnow(),
            "source": "ai",
        })
    except Exception:
        pass

    return ChatResponse(reply=[reply], conversation_id=conv_id)
