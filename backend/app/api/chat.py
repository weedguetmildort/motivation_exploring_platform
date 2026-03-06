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
from ..services.search import get_chat_response_with_search

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


def get_chat_response(messages: list[dict]) -> str:
    try:
        resp = _client.chat.completions.create(
            model=os.getenv("UF_OPENAI_API_MODEL"),
            messages=messages,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream AI request failed")

def _save_message(col, role: str, user: UserPublic, conv_id: str, content) -> None:
    try:
        col.insert_one({
            "conversation_id": conv_id,
            "role": role,
            "user_id": user.id,
            "user_email": user.email,
            "content": content,
            "created_at": datetime.utcnow(),
            "source": "web" if role == "user" else "ai",
        })
    except Exception:
        pass


# Gets responses from Agents A and B. Each agent can be called seperately. Agent B review's Agent A's answers by default
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

    # Agent A: sees full prior conversation
    reply_a = ""
    reply_b = ""

    if run_agent_a:
        system_instruction = (
            "You are a helpful assistant who generates clear and concise answers "
            "to help students answer some quiz questions."
        )
        messages_a = [
            {"role": "system", "content": system_instruction},
            *history,
            {"role": "user", "content": req.message},
        ]
        reply_a = get_chat_response(messages_a)

    # Agent B: sees full prior conversation plus Agent A's new response
    if run_agent_b:
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

        reply_b = get_chat_response(messages_b)


    replies: list[str] = []
    if run_agent_a:
        replies.append(reply_a)
    if run_agent_b:
        replies.append(reply_b)

    # Build labeled version for storage so history preserves agent identity
    replies_to_store: list[str] = []
    if run_agent_a:
        replies_to_store.append(f"[AGENT A] {reply_a}")
    if run_agent_b:
        replies_to_store.append(f"[AGENT B] {reply_b}")

    #Insert the user message. Wait to see if any of the chatbots gave an error to not save partial conversation info
    _save_message(request.app.state.messages, "user", user, conv_id, req.message)

    # Insert selected agent replies as a single assistant document
    _save_message(request.app.state.messages, "assistant", user, conv_id, replies_to_store)

    return ChatResponse(reply=replies, conversation_id=conv_id)


class FollowupRequest(BaseModel):
    last_ai_message: str

class FollowupResponse(BaseModel):
    questions: list[str]

# Special routing to generate follow up questions. 
# Does not correspond to agent responses to user
@router.post("/chat/addon/followup", response_model=FollowupResponse)
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

    raw = get_chat_response([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

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

# Returns chat with inline citation links embedded in the response text
@router.post("/chat/links", response_model=ChatResponse)
async def chat_with_embedded_links(
    req: ChatRequest,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    if not _UF_API_KEY:
        raise HTTPException(status_code=500, detail="Backend missing UF_OPENAI_API_KEY")

    conv_id = req.conversation_id or str(uuid.uuid4())

    # Fetch history BEFORE inserting the new user message
    history = get_last_exchange(request.app.state.messages, conv_id)

    _save_message(request.app.state.messages, "user", user, conv_id, req.message)

    system_instruction = (
        "You are a helpful assistant who generates clear and concise answers "
        "to help students answer some quiz questions. "
        "Use web searches to gather information and cite sources inline."
    )
    try:
        output = get_chat_response_with_search(
            client=_client,
            model=os.getenv("UF_OPENAI_API_MODEL"),
            messages=[
                {"role": "system", "content": system_instruction},
                *history,
                {"role": "user", "content": req.message},
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream AI request failed: {e}")

    reply = output["reply"]
    _save_message(request.app.state.messages, "assistant", user, conv_id, [reply])

    return ChatResponse(reply=[reply], conversation_id=conv_id)

#Default Behavior
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

    _save_message(request.app.state.messages, "user", user, conv_id, req.message)

    system_instruction = (
        "You are a helpful assistant who generates clear and concise answers "
        "to help students answer some quiz questions."
    )
    reply = get_chat_response([
        {"role": "system", "content": system_instruction},
        *history,
        {"role": "user", "content": req.message},
    ])

    _save_message(request.app.state.messages, "assistant", user, conv_id, [reply])

    return ChatResponse(reply=[reply], conversation_id=conv_id)
