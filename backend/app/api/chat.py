import os
import uuid
import time
import json
import asyncio
from typing import Optional, AsyncGenerator
from pydantic import BaseModel
from openai import AsyncOpenAI
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from ..schemas.user import UserPublic
from ..schemas.message import AIMessageMetadata
from .auth import get_current_user
from ..services.chat import get_last_exchange, get_conversation_history as fetch_conversation_history
from ..services.search import get_chat_response_with_search
from ..services.followup import generate_followup_questions

router = APIRouter()

# Max tokens the AI may generate per response. 0 = no limit. Valid range: 1–4096 (model-dependent).
MAX_TOKENS: int = 1000

# Controls response randomness. 0.0 = fully deterministic, 2.0 = very random. Valid range: 0.0–2.0. Recommended: 0.0–1.0.
TEMPERATURE: float = 0.5


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    agents: list[str] = []


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


def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Event string."""
    return f"data: {json.dumps(data)}\n\n"


async def _stream_ai(messages: list[dict]) -> AsyncGenerator[str, None]:
    """Streams text delta tokens from the AI. Raises on failure."""
    stream = await _client.chat.completions.create(
        model=os.getenv("UF_OPENAI_API_MODEL"),
        messages=messages,
        stream=True,
        temperature=TEMPERATURE,
        **({"max_tokens": MAX_TOKENS} if MAX_TOKENS > 0 else {}),
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


async def get_chat_response(messages: list[dict]) -> str:
    try:
        resp = await _client.chat.completions.create(
            model=os.getenv("UF_OPENAI_API_MODEL"),
            messages=messages,
            temperature=TEMPERATURE,
            **({"max_tokens": MAX_TOKENS} if MAX_TOKENS > 0 else {}),
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
            temperature=TEMPERATURE,
            **({"max_tokens": MAX_TOKENS} if MAX_TOKENS > 0 else {}),
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


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


# Gets responses from Agents A and B. Each agent can be called separately.
@router.post("/chat/double")
async def double_chat(
    req: ChatRequest,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    if not _UF_API_KEY:
        raise HTTPException(status_code=500, detail="Backend missing UF_OPENAI_API_KEY")

    conv_id = req.conversation_id or str(uuid.uuid4())

    requested_agents = {a.lower() for a in req.agents}
    valid_agents = {"agenta", "agentb"}
    selected_agents = requested_agents.intersection(valid_agents)
    if not selected_agents:
        selected_agents = valid_agents
    run_agent_a = "agenta" in selected_agents
    run_agent_b = "agentb" in selected_agents

    history = get_last_exchange(request.app.state.messages, conv_id)
    col = request.app.state.messages

    messages_a = [
        {"role": "system", "content": _BASE_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": req.message},
    ]
    system_b_with_a = (
        _BASE_SYSTEM_PROMPT +
        " Double check that the answers provided by [AGENT A] are correct, and if not, provide the correct answer."
    )

    async def generate() -> AsyncGenerator[str, None]:
        reply_a = ""
        reply_b = ""

        if run_agent_a:
            try:
                async for delta in _stream_ai(messages_a):
                    reply_a += delta
                    yield _sse({"type": "token", "agent": "A", "content": delta})
            except Exception:
                yield _sse({"type": "error", "detail": "Upstream AI request failed"})
                return

        if run_agent_b:
            if run_agent_a:
                messages_b = [
                    {"role": "system", "content": system_b_with_a},
                    *history,
                    {"role": "user", "content": req.message},
                    {"role": "assistant", "content": f"[AGENT A] {reply_a}"},
                ]
            else:
                messages_b = [
                    {"role": "system", "content": _BASE_SYSTEM_PROMPT},
                    *history,
                    {"role": "user", "content": req.message},
                ]
            try:
                async for delta in _stream_ai(messages_b):
                    reply_b += delta
                    yield _sse({"type": "token", "agent": "B", "content": delta})
            except Exception:
                yield _sse({"type": "error", "detail": "Upstream AI request failed"})
                return

        replies_to_store = []
        if run_agent_a:
            replies_to_store.append(f"[AGENT A] {reply_a}")
        if run_agent_b:
            replies_to_store.append(f"[AGENT B] {reply_b}")
        _save_message(col, "user", user, conv_id, req.message)
        _save_message(col, "assistant", user, conv_id, replies_to_store)

        yield _sse({"type": "done", "conversation_id": conv_id})

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


class FollowupResponse(BaseModel):
    questions: list[str]


@router.post("/chat/followup")
async def followup_quiz_chat(
    req: ChatRequest,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    if not _UF_API_KEY:
        raise HTTPException(status_code=500, detail="Backend missing UF_OPENAI_API_KEY")

    conv_id = req.conversation_id or str(uuid.uuid4())
    history = get_last_exchange(request.app.state.messages, conv_id)
    col = request.app.state.messages

    messages = [
        {"role": "system", "content": _BASE_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": req.message},
    ]

    async def generate() -> AsyncGenerator[str, None]:
        full_reply = ""

        try:
            async for delta in _stream_ai(messages):
                full_reply += delta
                yield _sse({"type": "token", "content": delta})
        except Exception:
            yield _sse({"type": "error", "detail": "Upstream AI request failed"})
            return

        # Save messages and generate follow-up questions concurrently (option 5)
        save_user = asyncio.create_task(asyncio.to_thread(_save_message, col, "user", user, conv_id, req.message))
        save_asst = asyncio.create_task(asyncio.to_thread(_save_message, col, "assistant", user, conv_id, [full_reply]))
        followup_questions = await generate_followup_questions(full_reply, get_chat_response)
        await asyncio.gather(save_user, save_asst)

        yield _sse({"type": "followup", "questions": followup_questions})
        yield _sse({"type": "done", "conversation_id": conv_id})

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


# Returns chat with inline citation links embedded in the response text.
# Waits for search + generation + citation injection, then streams the reply word-by-word.
@router.post("/chat/links")
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

    async def generate() -> AsyncGenerator[str, None]:
        try:
            output = await get_chat_response_with_search(
                client=_client,
                model=os.getenv("UF_OPENAI_API_MODEL"),
                messages=[
                    {"role": "system", "content": system_instruction},
                    *history,
                    {"role": "user", "content": req.message},
                ],
            )
        except Exception as e:
            yield _sse({"type": "error", "detail": f"Upstream AI request failed: {e}"})
            return

        reply = output["reply"]

        # Stream the citation-injected reply word-by-word
        words = reply.split(" ")
        for i, word in enumerate(words):
            yield _sse({"type": "token", "content": word + ("" if i == len(words) - 1 else " ")})

        _save_message(request.app.state.messages, "user", user, conv_id, req.message)
        _save_message(request.app.state.messages, "assistant", user, conv_id, [reply])
        yield _sse({"type": "done", "conversation_id": conv_id})

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


# Default behavior
@router.post("/chat/{quiz_id}")
async def chat(
    quiz_id: str,
    req: ChatRequest,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    if not _UF_API_KEY:
        raise HTTPException(status_code=500, detail="Backend missing UF_OPENAI_API_KEY")

    conv_id = req.conversation_id or str(uuid.uuid4())
    history = get_last_exchange(request.app.state.messages, conv_id)
    col = request.app.state.messages

    messages = [
        {"role": "system", "content": _BASE_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": req.message},
    ]

    async def generate() -> AsyncGenerator[str, None]:
        full_reply = ""
        try:
            async for delta in _stream_ai(messages):
                full_reply += delta
                yield _sse({"type": "token", "content": delta})
        except Exception:
            yield _sse({"type": "error", "detail": "Upstream AI request failed"})
            return

        _save_message(col, "user", user, conv_id, req.message)
        _save_message(col, "assistant", user, conv_id, [full_reply])
        yield _sse({"type": "done", "conversation_id": conv_id})

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


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
