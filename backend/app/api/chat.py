import os
import uuid
from pydantic import BaseModel
from openai import OpenAI
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from ..schemas.user import UserPublic
from .auth import get_current_user

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None

class ChatResponse(BaseModel):
    reply: str
    conversation_id: str

# Initialize OpenAI client with UF proxy settings (from env)
_UF_API_KEY = os.getenv("UF_OPENAI_API_KEY")
_UF_BASE_URL = os.getenv("UF_OPENAI_BASE_URL", "https://api.ai.it.ufl.edu")
_client = OpenAI(api_key=_UF_API_KEY, base_url=_UF_BASE_URL)

@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    if not _UF_API_KEY:
        # surface a clear backend misconfiguration error
        raise HTTPException(status_code=500, detail="Backend missing UF_OPENAI_API_KEY")
    
    # pick or create a conversation id
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
        # don't fail the chat if logging fails
        pass

    # Get assistant reply from UF proxy
    try:
        system_instruction = (
            "You are a helpful assistant who generates clear and concise answers "
            "to help students answer some quiz questions."
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": req.message},
        ]

        # Send the user’s message to the proxy; keep it simple (non-streaming)
        resp = _client.chat.completions.create(
            model=os.getenv("UF_OPENAI_API_MODEL"),
            messages=messages,
        )
        reply = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        # Don’t leak internals to the client
        raise HTTPException(status_code=502, detail="Upstream AI request failed")
    

    # Insert assistant message
    try:
        request.app.state.messages.insert_one({
            "conversation_id": conv_id,
            "role": "assistant",
            "user_id": user.id,
            "user_email": user.email,
            "content": reply,
            "created_at": datetime.utcnow(),
            "source": "ai",
        })
    except Exception:
        pass


    return ChatResponse(reply=reply, conversation_id=conv_id)
