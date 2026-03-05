import os
import re
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
    agents: list[str] = []

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
    
    # Determine which agents to run
    requested_agents = {a.lower() for a in req.agents}
    valid_agents = {"agenta", "agentb"}
    selected_agents = requested_agents.intersection(valid_agents)
    if not selected_agents:
        selected_agents = valid_agents
    run_agent_a = "agenta" in selected_agents
    run_agent_b = "agentb" in selected_agents

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
    reply_a = ""
    reply_b = ""

    if run_agent_a:
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
            reply_a = (resp.choices[0].message.content or "").strip()
        except Exception:
            raise HTTPException(status_code=502, detail="Upstream AI request failed")

    # Agent B: sees full prior conversation plus Agent A's new response
    if run_agent_b:
        try:
            if run_agent_a:
                system_instruction_b = (
                    "You are a helpful assistant who generates clear and concise answers "
                    "to help students answer some quiz questions. "
                    "Double check that the answers provided by [AGENT A] are correct, and if not, provide the correct answer."
                )
                messages_b = [
                    {"role": "system", "content": system_instruction_b},
                    *history,
                    {"role": "user", "content": req.message},
                    {"role": "assistant", "content": f"[AGENT A] {reply_a}"},
                ]
            else:
                system_instruction_b = (
                    "You are a helpful assistant who generates clear and concise answers "
                    "to help students answer some quiz questions."
                )
                messages_b = [
                    {"role": "system", "content": system_instruction_b},
                    *history,
                    {"role": "user", "content": req.message},
                ]

            resp = _client.chat.completions.create(
                model=os.getenv("UF_OPENAI_API_MODEL"),
                messages=messages_b,
            )
            reply_b = (resp.choices[0].message.content or "").strip()
        except Exception:
            raise HTTPException(status_code=502, detail="Upstream AI request failed")

    replies: list[str] = []
    if run_agent_a:
        replies.append(reply_a)
    if run_agent_b:
        replies.append(reply_b)

    # Insert selected agent replies as a single assistant document
    try:
        request.app.state.messages.insert_one({
            "conversation_id": conv_id,
            "role": "assistant",
            "user_id": user.id,
            "user_email": user.email,
            "content": replies,
            "created_at": datetime.utcnow(),
            "source": "ai",
        })
    except Exception:
        pass

    return ChatResponse(reply=replies, conversation_id=conv_id)


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
