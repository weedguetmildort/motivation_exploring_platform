import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI

router = APIRouter()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

# Initialize OpenAI client with UF proxy settings (from env)
_UF_API_KEY = os.getenv("UF_OPENAI_API_KEY")
_UF_BASE_URL = os.getenv("UF_OPENAI_BASE_URL", "https://api.ai.it.ufl.edu")
_client = OpenAI(api_key=_UF_API_KEY, base_url=_UF_BASE_URL)

@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not _UF_API_KEY:
        # surface a clear backend misconfiguration error
        raise HTTPException(status_code=500, detail="Backend missing UF_OPENAI_API_KEY")
    try:
        # Send the user’s message to the proxy; keep it simple (non-streaming)
        resp = _client.chat.completions.create(
            model="llama-3.3-70b-instruct",
            messages=[{"role": "user", "content": req.message}],
        )
        reply = (resp.choices[0].message.content or "").strip()
        return ChatResponse(reply=reply)
    except Exception as e:
        # Don’t leak internals to the client
        raise HTTPException(status_code=502, detail="Upstream AI request failed")
    # Simple echo for now — replace with real logic later
    # return ChatResponse(reply=f"Echo: {req.message}")