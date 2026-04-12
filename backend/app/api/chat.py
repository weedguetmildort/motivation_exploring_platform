import os
import uuid
import time
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from typing import Optional
from ..schemas.user import UserPublic
from ..schemas.message import AIMessageMetadata
from .auth import get_current_user
from ..services.chat import get_last_exchange, get_conversation_history as fetch_conversation_history
from ..services.search import get_chat_response_with_search
from ..services.followup import generate_followup_questions

router = APIRouter()

class AnswerChoice(BaseModel):
    id: str
    label: str

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    agents: list[str] = Field(default_factory=list)
    answer_incorrectly: bool = False
    question_text: str | None = None
    answer_choices: list[AnswerChoice] = Field(default_factory=list)

class ChatResponse(BaseModel):
    reply: list[str]
    conversation_id: str
    metadata: Optional[list[AIMessageMetadata]] = None


def _extract_metadata_from_response(
    resp,
    model_version: Optional[str] = None,
) -> AIMessageMetadata:
    return AIMessageMetadata(
        model_version=model_version or getattr(resp, "model", None),
        tokens_used=getattr(resp.usage, "total_tokens", None) if resp.usage else None,
        input_tokens=getattr(resp.usage, "prompt_tokens", None) if resp.usage else None,
        output_tokens=getattr(resp.usage, "completion_tokens", None) if resp.usage else None,
    )


class FollowupChatResponse(BaseModel):
    reply: list[str]
    conversation_id: str
    followup_questions: list[str]

# Initialize OpenAI client with UF proxy settings (from env)
_UF_API_KEY = os.getenv("UF_OPENAI_API_KEY")
_UF_BASE_URL = os.getenv("UF_OPENAI_BASE_URL", "https://api.ai.it.ufl.edu")
_client = AsyncOpenAI(api_key=_UF_API_KEY, base_url=_UF_BASE_URL, timeout=60.0)

_BASE_SYSTEM_PROMPT = (
    "You are a helpful assistant who generates clear and concise answers "
    "to help students answer some quiz questions."
    "Go through the explanation first, and only then provide the solution at the end."
)

def _format_question_with_choices(req: ChatRequest) -> str:
    parts: list[str] = []

    if req.question_text:
        parts.append(f"Question:\n{req.question_text}")

    if req.answer_choices:
        formatted_choices = "\n".join(
            [f"{choice.id}. {choice.label}" for choice in req.answer_choices]
        )
        parts.append(f"Answer choices:\n{formatted_choices}")

    if req.message:
        parts.append(f"Student message:\n{req.message}")

    return "\n\n".join(parts).strip()


def _build_system_instruction(answer_incorrectly: bool, has_choices: bool) -> str:
    if answer_incorrectly and has_choices:
        return (
            "You are a helpful assistant helping a student with a multiple-choice question. "
            "The user will provide a question and a fixed list of answer choices. "
            "You MUST choose exactly ONE of the provided answer choices. "
            "You MUST NOT invent a new answer choice. "
            "You MUST choose an incorrect answer choice from the provided list. "
            "You must sound confident and explain why your chosen answer is correct. "
            "Do NOT say that you are unsure. "
            "Do NOT mention that your answer is intentionally incorrect. "
            "Start your response by clearly naming the selected answer choice."
        )

    if answer_incorrectly:
        return (
            "You are a helpful assistant helping a student with a question. "
            "Respond confidently with an incorrect answer and explain it as if it were correct. "
            "Do NOT say that you are unsure or that you may be wrong."
        )

    if has_choices:
        return (
            "You are a helpful assistant who helps students answer multiple-choice questions. "
            "Carefully analyze the question and the provided answer choices. "
            "Choose exactly ONE of the provided answer choices. "
            "Do NOT invent a new answer choice. "
            "Explain your reasoning clearly. "
            "Start your response by clearly naming the selected answer choice."
        )

    return (
        "You are a helpful assistant who helps students answer questions. "
        "Explain your reasoning clearly."
    )


async def get_chat_response(messages: list[dict]) -> str:
    try:
        resp = await _client.chat.completions.create(
            model=os.getenv("UF_OPENAI_API_MODEL"),
            messages=messages,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream AI request failed")


async def get_chat_response_with_metadata(
    messages: list[dict],
    model_version: Optional[str] = None,
) -> tuple[str, AIMessageMetadata]:
    try:
        start_time = time.time()
        resp = await _client.chat.completions.create(
            model=model_version or os.getenv("UF_OPENAI_API_MODEL"),
            messages=messages,
        )
        processing_time_ms = int((time.time() - start_time) * 1000)
        reply = (resp.choices[0].message.content or "").strip()

        metadata = _extract_metadata_from_response(resp, model_version)
        metadata.processing_time_ms = processing_time_ms
        return reply, metadata
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream AI request failed")


def _save_message(
    col,
    role: str,
    user: UserPublic,
    conv_id: str,
    content,
    metadata=None,
) -> None:
    try:
        doc = {
            "conversation_id": conv_id,
            "role": role,
            "user_id": user.id,
            "user_email": user.email,
            "content": content,
            "created_at": datetime.utcnow(),
            "source": "web" if role == "user" else "ai",
        }
        if metadata is not None:
            doc["metadata"] = metadata
        col.insert_one(doc)
    except Exception:
        pass


# Gets responses from Agents A and B. Each agent can be called separately.
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

    # Determine which agents to run
    requested_agents = {a.lower() for a in req.agents}
    valid_agents = {"agenta", "agentb"}
    selected_agents = requested_agents.intersection(valid_agents)
    if not selected_agents:
        selected_agents = valid_agents
    run_agent_a = "agenta" in selected_agents
    run_agent_b = "agentb" in selected_agents

    history = get_last_exchange(request.app.state.messages, conv_id)
    prompt_content = _format_question_with_choices(req)
    reply_a = ""
    reply_b = ""
    metadata_a: Optional[AIMessageMetadata] = None
    metadata_b: Optional[AIMessageMetadata] = None


    if run_agent_a:
        system_instruction_a = _build_system_instruction(
        answer_incorrectly=req.answer_incorrectly,
        has_choices=len(req.answer_choices) > 0,
        )

        messages_a = [
            {"role": "system", "content": system_instruction_a},
            *history,
            {"role": "user", "content": prompt_content},
        ]
        reply_a, metadata_a = await get_chat_response_with_metadata(messages_a, model_version)

    if run_agent_b:
        if run_agent_a:
            system_instruction_b = (
                _BASE_SYSTEM_PROMPT + 
                " Double check that the answers provided by [AGENT A] are correct, and if not, provide the correct answer."
            )
            messages_b = [
                {"role": "system", "content": system_instruction_b},
                *history,
                {"role": "user", "content": prompt_content},
                {"role": "assistant", "content": f"[AGENT A] {reply_a}"},
            ]
        else:
            system_instruction_b = _build_system_instruction(
                answer_incorrectly=req.answer_incorrectly,
                has_choices=len(req.answer_choices) > 0,)
            messages_b = [
                {"role": "system", "content": system_instruction_b},
                *history,
                {"role": "user", "content": prompt_content},
            ]

        reply_b, metadata_b = await get_chat_response_with_metadata(messages_b, model_version)

    replies: list[str] = []
    metadata_list: list[AIMessageMetadata] = []
    replies_to_store: list[str] = []
    agents_meta: list[dict] = []

    if run_agent_a:
        replies.append(reply_a)
        replies_to_store.append(f"[AGENT A] {reply_a}")
        if metadata_a:
            metadata_list.append(metadata_a)
            agents_meta.append(metadata_a.model_dump(exclude_none=True))

    if run_agent_b:
        replies.append(reply_b)
        replies_to_store.append(f"[AGENT B] {reply_b}")
        if metadata_b:
            metadata_list.append(metadata_b)
            agents_meta.append(metadata_b.model_dump(exclude_none=True))

    _save_message(request.app.state.messages, "user", user, conv_id, req.message)

    # Save assistant reply with per-agent metadata bundled for history/analysis.
    _save_message(
        request.app.state.messages,
        "assistant",
        user,
        conv_id,
        replies_to_store,
        metadata={"agents": agents_meta} if agents_meta else None,
    )

    return ChatResponse(
        reply=replies,
        conversation_id=conv_id,
        metadata=metadata_list or None,
    )

class FollowupResponse(BaseModel):
    questions: list[str]


@router.post("/chat/followup", response_model=FollowupChatResponse)
async def followup_quiz_chat(
    req: ChatRequest,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    if not _UF_API_KEY:
        raise HTTPException(status_code=500, detail="Backend missing UF_OPENAI_API_KEY")

    conv_id = req.conversation_id or str(uuid.uuid4())
    history = get_last_exchange(request.app.state.messages, conv_id)

    prompt_content = _format_question_with_choices(req)
    reply = await get_chat_response([
        {"role": "system", "content": _BASE_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": prompt_content},
    ])

    _save_message(request.app.state.messages, "user", user, conv_id, req.message)
    _save_message(request.app.state.messages, "assistant", user, conv_id, [reply])

    followup_questions = await generate_followup_questions(reply, get_chat_response)

    return FollowupChatResponse(reply=[reply], conversation_id=conv_id, followup_questions=followup_questions)


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
    history = get_last_exchange(request.app.state.messages, conv_id)

    system_instruction = (
        _BASE_SYSTEM_PROMPT +
        " Use web searches to gather information and cite sources inline."
        "Prioritize academic and institutional sources; avoid blog posts, news articles, or unverifiable sources."
        "Prefer sources with stable, long-lived URLs."

        "Preferred sources:"
        "- Wikipedia (en.wikipedia.org)"
        "- Encyclopaedia Britannica (britannica.com)"
        "- Government sites (.gov such as CDC, NIH, NASA, NIST)"
        "- University and educational sites (.edu)"
        "- MIT OpenCourseWare (ocw.mit.edu)"
        "- PubMed / NCBI (ncbi.nlm.nih.gov) for biomedical topics"
        "- arXiv (arxiv.org) for physics, mathematics, and computer science preprints"
        "- Wolfram MathWorld (mathworld.wolfram.com) for mathematics"
        "- Stanford Encyclopedia of Philosophy (plato.stanford.edu) for philosophy"
        "- IEEE Xplore (ieeexplore.ieee.org) for engineering and computer science"
        "- ACM Digital Library (dl.acm.org) for computer science research"
    )

    try:
        output = await get_chat_response_with_search(
            client=_client,
            model=os.getenv("UF_OPENAI_API_MODEL"),
            messages=[
                {"role": "system", "content": system_instruction},
                *history,
                {"role": "user", "content": _format_question_with_choices(req)},
            ],
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Upstream AI request failed: {e}")

    reply = output["reply"]
    _save_message(request.app.state.messages, "user", user, conv_id, req.message)
    _save_message(request.app.state.messages, "assistant", user, conv_id, [reply])

    return ChatResponse(reply=[reply], conversation_id=conv_id)


# Default behavior
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

    history = get_last_exchange(request.app.state.messages, conv_id)

    has_choices = len(req.answer_choices) > 0
    system_instruction = _build_system_instruction(
        answer_incorrectly=req.answer_incorrectly,
        has_choices=has_choices,
    )
    prompt_content = _format_question_with_choices(req)

    reply, metadata = await get_chat_response_with_metadata([
        {"role": "system", "content": system_instruction},
        *history,
        {"role": "user", "content": prompt_content},
    ], model_version)

    _save_message(request.app.state.messages, "user", user, conv_id, req.message)
    _save_message(
        request.app.state.messages,
        "assistant",
        user,
        conv_id,
        [reply],
        metadata=metadata.model_dump(exclude_none=True),
    )

    return ChatResponse(
        reply=[reply],
        conversation_id=conv_id,
        metadata=[metadata],
    )


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


@router.get("/chat/get_history/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    conversation_id: str,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    try:
        docs = fetch_conversation_history(request.app.state.messages, conversation_id)

        if not docs:
            return ConversationHistoryResponse(conversation_id=conversation_id, messages=[])

        if docs and docs[0].get("user_id") != user.id:
            raise HTTPException(status_code=403, detail="Unauthorized access to conversation")

        messages = []
        for doc in docs:
            metadata_dict = doc.get("metadata")
            metadata = None
            if metadata_dict:
                try:
                    if isinstance(metadata_dict, dict) and "agents" not in metadata_dict:
                        metadata = AIMessageMetadata(**metadata_dict)
                    elif isinstance(metadata_dict, dict) and "agents" in metadata_dict:
                        metadata = AIMessageMetadata(
                            custom_metadata={"agents": metadata_dict.get("agents", [])}
                        )
                except Exception:
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
            messages=messages,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve conversation: {str(e)}")


@router.get("/chat/load_user_history/{conversation_id}", response_model=UserConversationHistoryResponse)
async def load_user_history(
    conversation_id: str,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    all_docs = fetch_conversation_history(request.app.state.messages, conversation_id)
    if not all_docs:
        return UserConversationHistoryResponse(conversation_id=conversation_id, messages=[])
    if all_docs[0].get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="Unauthorized access to conversation")

    user_docs = [d for d in all_docs if d["role"] == "user"][-5:]
    assistant_docs = [d for d in all_docs if d["role"] == "assistant"][-5:]
    combined = sorted(user_docs + assistant_docs, key=lambda d: d["created_at"])

    messages = [UserMessageData(role=d["role"], content=d["content"]) for d in combined]
    return UserConversationHistoryResponse(conversation_id=conversation_id, messages=messages)
