import os
import uuid
import json
import asyncio
import time
from typing import AsyncGenerator, Callable, Optional
from openai import AsyncOpenAI
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse

from ..schemas.user import UserPublic
from ..schemas.message import AIMessageMetadata
from ..schemas.chat import (
    ChatRequest, ChatResponse, FollowupChatResponse, FollowupResponse,
    UserMessageData, UserConversationHistoryResponse,
    ConversationMessageData, ConversationHistoryResponse,
)
from .auth import get_current_user
from ..services.chat import get_last_exchange, get_conversation_history as fetch_conversation_history
from ..services.search import get_chat_response_with_search
from ..services.followup import generate_followup_questions

router = APIRouter()

# Max tokens the AI may generate per response. 0 = no limit. Valid range: 1–4096 (model-dependent).
MAX_TOKENS: int = 1000

# Controls response randomness. 0.0 = fully deterministic, 2.0 = very random. Valid range: 0.0–2.0. Recommended: 0.0–1.0.
TEMPERATURE: float = 0.5



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


# Not currently used — all endpoints stream tokens via _stream_ai / _standard_stream.
# Restore this if any endpoint switches back to a single blocking AI call that needs
# metadata (latency, token counts, model version) attached to the stored message.
# To use: call alongside _client.chat.completions.create(stream=False), pass the
# response object and optionally a model_version override, then include the returned
# AIMessageMetadata in the _save_message(..., metadata=...) call.
def _extract_metadata_from_response(
    resp,
    model_version: Optional[str] = None,
) -> AIMessageMetadata:
    return AIMessageMetadata(
        model_version=model_version or getattr(resp, "model", None),
        tokens_used=getattr(resp.usage, "total_tokens", None) if resp.usage else None,
        input_tokens=getattr(resp.usage, "prompt_tokens", None) if resp.usage else None,
        output_tokens=getattr(resp.usage, "completion_tokens", None) if resp.usage else None,
        processing_time_ms=None,  # populate with int((time.time() - start_time) * 1000) at call site
    )


def _build_standard_messages(
    history: list[dict],
    user_message: str,
    system_prompt: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> list[dict]:
    """Build the standard [system, *history, user] message list.

    agent_name: if provided, appends 'You are {agent_name}.' to the system prompt
    so the agent is aware of its identity in multi-agent contexts.
    """
    base = system_prompt or _BASE_SYSTEM_PROMPT
    if agent_name:
        base = f"{base}\nYou are {agent_name}."
    return [
        {"role": "system", "content": base},
        *history,
        {"role": "user", "content": user_message},
    ]


async def _stream_agent_tokens(
    messages: list[dict],
    agent_tag: Optional[str] = None,
) -> AsyncGenerator[tuple[bool, str, str], None]:
    """Core token-streaming helper. Yields (is_error, delta, sse_str) tuples.

    On success: is_error=False, delta=token text, sse_str=token SSE event.
    On failure: is_error=True, delta='', sse_str=error SSE event (then stops).
    Callers accumulate delta to reconstruct the full reply.
    """
    try:
        async for delta in _stream_ai(messages):
            event: dict = {"type": "token", "content": delta}
            if agent_tag:
                event["agent"] = agent_tag
            yield False, delta, _sse(event)
    except Exception:
        yield True, "", _sse({"type": "error", "detail": "Upstream AI request failed"})


async def _standard_stream(
    messages: list[dict],
    col,
    user: UserPublic,
    conv_id: str,
    user_message: str,
    after_done: Optional[Callable[[str], AsyncGenerator[str, None]]] = None,
    request: Optional[Request] = None,
) -> AsyncGenerator[str, None]:
    """Stream tokens, fire-and-forget saves, emit done, then optionally yield from after_done."""
    full_reply = ""
    async for is_error, delta, sse in _stream_agent_tokens(messages):
        yield sse
        if is_error:
            return
        full_reply += delta

    asyncio.create_task(asyncio.to_thread(_save_message, col, "user", user, conv_id, user_message))
    asyncio.create_task(asyncio.to_thread(_save_message, col, "assistant", user, conv_id, [full_reply]))
    yield _sse({"type": "done", "conversation_id": conv_id})

    if after_done and not (request and await request.is_disconnected()):
        async for event in after_done(full_reply):
            yield event


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

    col = request.app.state.messages
    # Each agent gets only its own last reply as history — no cross-agent context.
    # This simplifies @mention routing: each agent's memory is isolated to its own turns.
    history_a, history_b = await asyncio.gather(
        asyncio.to_thread(get_last_exchange, col, conv_id, "[AGENT A]"),
        asyncio.to_thread(get_last_exchange, col, conv_id, "[AGENT B]"),
    )
    messages_a = _build_standard_messages(history_a, req.message, agent_name="Agent A")
    messages_b = _build_standard_messages(history_b, req.message, agent_name="Agent B")

    async def generate() -> AsyncGenerator[str, None]:
        reply_a = ""
        reply_b = ""

        # _stream_agent_tokens reuses the core try/except streaming logic from _standard_stream.
        # We keep the save logic here because double needs one combined assistant doc so that
        # _format_assistant / get_last_exchange(agent_prefix=...) can extract per-agent replies next turn.
        if run_agent_a:
            async for is_error, delta, sse in _stream_agent_tokens(messages_a, agent_tag="A"):
                yield sse
                if is_error:
                    return
                reply_a += delta

        if run_agent_b:
            async for is_error, delta, sse in _stream_agent_tokens(messages_b, agent_tag="B"):
                yield sse
                if is_error:
                    return
                reply_b += delta

        replies_to_store = []
        if run_agent_a:
            replies_to_store.append(f"[AGENT A] {reply_a}")
        if run_agent_b:
            replies_to_store.append(f"[AGENT B] {reply_b}")

        asyncio.create_task(asyncio.to_thread(_save_message, col, "user", user, conv_id, req.message))
        asyncio.create_task(asyncio.to_thread(_save_message, col, "assistant", user, conv_id, replies_to_store))

        yield _sse({"type": "done", "conversation_id": conv_id})

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/chat/followup")
async def followup_quiz_chat(
    req: ChatRequest,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    if not _UF_API_KEY:
        raise HTTPException(status_code=500, detail="Backend missing UF_OPENAI_API_KEY")

    conv_id = req.conversation_id or str(uuid.uuid4())
    history = await asyncio.to_thread(get_last_exchange, request.app.state.messages, conv_id)
    col = request.app.state.messages
    messages = _build_standard_messages(history, req.message)

    async def after_done(full_reply: str) -> AsyncGenerator[str, None]:
        async for delta in generate_followup_questions(full_reply, _stream_ai):
            yield _sse({"type": "followup", "token": delta})

    return StreamingResponse(
        _standard_stream(messages, col, user, conv_id, req.message, after_done=after_done, request=request),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


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
    
    # OPTIMIZATION: Non-blocking DB read for history
    history = await asyncio.to_thread(get_last_exchange, request.app.state.messages, conv_id)

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
                messages=_build_standard_messages(history, req.message, system_prompt=system_instruction),
            )
        except Exception as e:
            yield _sse({"type": "error", "detail": f"Upstream AI request failed: {e}"})
            return

        reply = output["reply"]

        # Stream the citation-injected reply word-by-word
        words = reply.split(" ")
        for i, word in enumerate(words):
            yield _sse({"type": "token", "content": word + ("" if i == len(words) - 1 else " ")})

        # OPTIMIZATION: Non-blocking database saves (fire-and-forget)
        asyncio.create_task(asyncio.to_thread(_save_message, request.app.state.messages, "user", user, conv_id, req.message))
        asyncio.create_task(asyncio.to_thread(_save_message, request.app.state.messages, "assistant", user, conv_id, [reply]))
        
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
    history = await asyncio.to_thread(get_last_exchange, request.app.state.messages, conv_id)
    col = request.app.state.messages
    messages = _build_standard_messages(history, req.message)

    return StreamingResponse(
        _standard_stream(messages, col, user, conv_id, req.message),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/chat/get_history/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    conversation_id: str,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    try:
        # OPTIMIZATION: Non-blocking DB read
        docs = await asyncio.to_thread(fetch_conversation_history, request.app.state.messages, conversation_id)

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
    # OPTIMIZATION: Non-blocking DB read
    all_docs = await asyncio.to_thread(fetch_conversation_history, request.app.state.messages, conversation_id)
    
    if not all_docs:
        return UserConversationHistoryResponse(conversation_id=conversation_id, messages=[])
    if all_docs[0].get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="Unauthorized access to conversation")

    user_docs = [d for d in all_docs if d["role"] == "user"][-5:]
    assistant_docs = [d for d in all_docs if d["role"] == "assistant"][-5:]
    combined = sorted(user_docs + assistant_docs, key=lambda d: d["created_at"])

    messages = [UserMessageData(role=d["role"], content=d["content"]) for d in combined]
    return UserConversationHistoryResponse(conversation_id=conversation_id, messages=messages)
