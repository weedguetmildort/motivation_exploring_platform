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

    # Retrieve the last exchange for conversation history
    last_user_c, last_asst_list = get_last_exchange(request.app.state.messages, conv_id)

    # Agent A: uses its own prior reply as context
    history_a = []
    if last_user_c and last_asst_list:
        history_a = [
            {"role": "user", "content": last_user_c},
            {"role": "assistant", "content": last_asst_list[0]},
        ]

    try:
        system_instruction = (
            "You are a helpful assistant who generates clear and concise answers "
            "to help students answer some quiz questions."
        )
        messages_a = [
            {"role": "system", "content": system_instruction},
            *history_a,
            {"role": "user", "content": req.message},
        ]
        resp = _client.chat.completions.create(
            model=os.getenv("UF_OPENAI_API_MODEL"),
            messages=messages_a,
        )
        reply = (resp.choices[0].message.content or "").strip()
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream AI request failed")

    # Agent B: uses its own prior reply as context, then sees Agent A's current response
    prior_b = last_asst_list[1] if len(last_asst_list) > 1 else (last_asst_list[0] if last_asst_list else None)
    history_b = []
    if last_user_c and prior_b:
        history_b = [
            {"role": "user", "content": last_user_c},
            {"role": "assistant", "content": prior_b},
        ]

    try:
        system_instruction_b = (
            "You are a helpful assistant who generates clear and concise answers "
            "to help students answer some quiz questions. "
            "Double check that the answer you provided is correct and if not, provide the correct answer."
        )
        messages_b = [
            {"role": "system", "content": system_instruction_b},
            *history_b,
            {"role": "user", "content": req.message},
            {"role": "assistant", "content": reply},
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

    # Retrieve the last exchange for conversation history
    last_user_c, last_asst_list = get_last_exchange(request.app.state.messages, conv_id)
    history = []
    if last_user_c and last_asst_list:
        history = [
            {"role": "user", "content": last_user_c},
            {"role": "assistant", "content": last_asst_list[0]},
        ]

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
