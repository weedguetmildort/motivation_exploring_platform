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
from ..services.search import _build_search_context, _inject_citation_links
# from ..services.search import _run_search, _filter_valid_urls  # external search disabled
from ..services.followup import generate_followup_questions

router = APIRouter()



# Max tokens the AI may generate per response. 0 = no limit. Valid range: 1–4096 (model-dependent).
MAX_TOKENS: int = 1000

# Controls response randomness. 0.0 = fully deterministic, 2.0 = very random. Valid range: 0.0–2.0. Recommended: 0.0–1.0.
TEMPERATURE: float = 0.5
# Lower temperature for double-agent mode so stochastic answer divergence is minimised
# and the style difference (intuitive vs. formal) is the dominant signal between agents.
DOUBLE_TEMPERATURE: float = 0.1


# Initialize OpenAI client with UF proxy settings (from env)
_UF_API_KEY = os.getenv("UF_OPENAI_API_KEY")
_UF_BASE_URL = os.getenv("UF_OPENAI_BASE_URL", "https://api.ai.it.ufl.edu")
_client = AsyncOpenAI(api_key=_UF_API_KEY, base_url=_UF_BASE_URL, timeout=60.0)

_BASE_SYSTEM_PROMPT = (
    "You are a helpful assistant who generates clear and concise answers "
    "to help students answer some quiz questions."
    "Go through the explanation first, and only then provide the solution at the end."
)

# Explanation-style personas for double-agent mode.
# Appended to each agent's system prompt to create a consistent, intentional difference
# in approach. Names stay neutral ("Agent A / B") to avoid priming students.
_AGENT_A_STYLE = (
    "Explain using intuition and everyday analogies — coin flips, card draws, "
    "real-world scenarios. Avoid mathematical notation. Make the concept feel "
    "natural and relatable before confirming the answer."
)
_AGENT_B_STYLE = (
    "Explain using precise mathematical reasoning. Define terms formally, "
    "show step-by-step logic, and use proper notation where helpful. "
    "Prioritize rigor and exactness."
)


def _sse(data: dict) -> str:
    """Format a dict as a Server-Sent Event string."""
    return f"data: {json.dumps(data)}\n\n"


async def _stream_ai(messages: list[dict], temperature: float = TEMPERATURE) -> AsyncGenerator[str, None]:
    """Streams text delta tokens from the AI. Raises on failure."""
    stream = await _client.chat.completions.create(
        model=os.getenv("UF_OPENAI_API_MODEL"),
        messages=messages,
        stream=True,
        temperature=temperature,
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


_background_tasks: set = set()


def _schedule_exchange_save(col, user: UserPublic, conv_id: str, user_message: str, assistant_reply: list, assistant_metadata: dict | None = None) -> None:
    """Fire-and-forget: save user then assistant message in a background thread.

    Saves user message first so its timestamp is strictly earlier than the
    assistant message. Called only after streaming completes successfully, so a
    failed stream leaves no partial records in the DB. Holds a strong reference
    to the task until it completes to prevent early GC by the event loop.
    """
    def _save() -> None:
        _save_message(col, "user", user, conv_id, user_message)
        _save_message(col, "assistant", user, conv_id, assistant_reply, assistant_metadata)

    task = asyncio.create_task(asyncio.to_thread(_save))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

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
    temperature: float = TEMPERATURE,
) -> AsyncGenerator[tuple[bool, str, str], None]:
    """Core token-streaming helper. Yields (is_error, delta, sse_str) tuples.

    On success: is_error=False, delta=token text, sse_str=token SSE event.
    On failure: is_error=True, delta='', sse_str=error SSE event (then stops).
    Callers accumulate delta to reconstruct the full reply.
    """
    try:
        async for delta in _stream_ai(messages, temperature=temperature):
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
    agent_tag: Optional[str] = None,
    reply_prefix: str = "",
    answer_incorrectly: bool = False,
    temperature: float = TEMPERATURE,
) -> AsyncGenerator[str, None]:
    """Stream tokens, fire-and-forget saves, emit done, then optionally yield from after_done.

    agent_tag: if set, each token SSE includes an "agent" field (used by double quiz).
    reply_prefix: prepended to the stored reply (e.g. "[AGENT A] " for double quiz).
    """
    full_reply = ""
    async for is_error, delta, sse in _stream_agent_tokens(messages, agent_tag=agent_tag, temperature=temperature):
        yield sse
        if is_error:
            return
        full_reply += delta

    stored_reply = f"{reply_prefix}{full_reply}" if reply_prefix else full_reply
    metadata = AIMessageMetadata(answer_incorrectly=answer_incorrectly).model_dump(exclude_none=True)
    _schedule_exchange_save(col, user, conv_id, user_message, [stored_reply], metadata)
    yield _sse({"type": "done", "conversation_id": conv_id})

    if after_done and not (request and await request.is_disconnected()):
        async for event in after_done(full_reply):
            yield event


async def _stream_into_queue(
    messages: list[dict],
    tag: str,
    queue: asyncio.Queue,
    temperature: float = TEMPERATURE,
) -> None:
    """Stream one agent's tokens into a shared queue for concurrent multi-agent rendering."""
    try:
        async for is_error, delta, sse in _stream_agent_tokens(messages, agent_tag=tag, temperature=temperature):
            await queue.put((is_error, delta, tag, sse))
            if is_error:
                return
    except asyncio.CancelledError:
        pass


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
    
    prompt_content = req.message

    system_instruction_a = _build_system_instruction(
        answer_incorrectly=req.answer_incorrectly,
        has_choices=len(req.answer_choices) > 0,
    )
    system_instruction_b = _build_system_instruction(
        answer_incorrectly=req.answer_incorrectly,
        has_choices=len(req.answer_choices) > 0,
    )

    messages_a = [
        {"role": "system", "content": f"{system_instruction_a}\nYou are Agent A.\n{_AGENT_A_STYLE}"},
        *history_a,
        {"role": "user", "content": prompt_content},
    ]

    messages_b = [
        {"role": "system", "content": f"{system_instruction_b}\nYou are Agent B.\n{_AGENT_B_STYLE}"},
        *history_b,
        {"role": "user", "content": prompt_content},
    ]

    # Single agent selected via @mention — reuse _standard_stream directly.
    if not (run_agent_a and run_agent_b):
        tag = "A" if run_agent_a else "B"
        msgs = messages_a if run_agent_a else messages_b
        return StreamingResponse(
            _standard_stream(msgs, col, user, conv_id, req.message,
                             agent_tag=tag, reply_prefix=f"[AGENT {tag}] ",
                             answer_incorrectly=req.answer_incorrectly,
                             temperature=DOUBLE_TEMPERATURE),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    # Both agents — run concurrently via shared queue.
    async def generate() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue = asyncio.Queue()
        replies = {"A": "", "B": ""}

        async def _run_both() -> None:
            await asyncio.gather(
                _stream_into_queue(messages_a, "A", queue, temperature=DOUBLE_TEMPERATURE),
                _stream_into_queue(messages_b, "B", queue, temperature=DOUBLE_TEMPERATURE),
            )

        task = asyncio.create_task(_run_both())
        task.add_done_callback(lambda _: queue.put_nowait(None))

        while True:
            item = await queue.get()
            if item is None:
                break
            is_error, delta, tag, sse = item
            yield sse
            if is_error:
                task.cancel()
                return
            replies[tag] += delta

        replies_to_store = [f"[AGENT A] {replies['A']}", f"[AGENT B] {replies['B']}"]
        metadata = AIMessageMetadata(answer_incorrectly=req.answer_incorrectly).model_dump(exclude_none=True)
        _schedule_exchange_save(col, user, conv_id, req.message, replies_to_store, assistant_metadata=metadata)
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
    system_instruction = _build_system_instruction(
        answer_incorrectly=req.answer_incorrectly,
        has_choices=len(req.answer_choices) > 0,
    )
    messages = _build_standard_messages(history, req.message, system_prompt=system_instruction)

    async def after_done(full_reply: str) -> AsyncGenerator[str, None]:
        async for delta in generate_followup_questions(full_reply, _stream_ai):
            yield _sse({"type": "followup", "token": delta})

    return StreamingResponse(
        _standard_stream(messages, col, user, conv_id, req.message, after_done=after_done, request=request, answer_incorrectly=req.answer_incorrectly),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# Streams tokens in real-time. Sends a citations SSE event before tokens so the
# frontend can inject [phrase][N] markers into real links once the stream is done.
@router.post("/chat/links")
async def chat_with_embedded_links(
    req: ChatRequest,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    if not _UF_API_KEY:
        raise HTTPException(status_code=500, detail="Backend missing UF_OPENAI_API_KEY")

    conv_id = req.conversation_id or str(uuid.uuid4())
    history = await asyncio.to_thread(get_last_exchange, request.app.state.messages, conv_id)

    system_instruction = (
        _build_system_instruction(
            answer_incorrectly=req.answer_incorrectly,
            has_choices=len(req.answer_choices) > 0,
        ) +
        " Use web searches to gather information and cite sources inline."
        #" Prioritize academic and institutional sources; avoid blog posts, news articles, or unverifiable sources."
        #" Prefer sources with stable, long-lived URLs."
    )

    async def generate() -> AsyncGenerator[str, None]:
        # External web search disabled — citations come from DB links only.
        # To re-enable: uncomment _run_search/_filter_valid_urls imports and restore lines below.
        # try:
        #     raw_web = await _run_search(req.message)
        # except Exception as e:
        #     yield _sse({"type": "error", "detail": f"Search failed: {e}"})
        #     return

        curated = [
            {"title": l.get("title", ""), "url": l.get("url", ""), "snippet": l.get("description", "")}
            for l in getattr(request.app.state, "knowledge_links", [])
            if l.get("url")
        ]
        augmented_messages, citations = _build_search_context(
            _build_standard_messages(history, req.message, system_prompt=system_instruction),
            curated,  # was: curated + raw_web
        )

        # validation_task = asyncio.create_task(_filter_valid_urls(raw_web))  # disabled with search

        if citations:
            yield _sse({"type": "citations", "citations": citations})

        full_reply = ""
        async for is_error, delta, sse in _stream_agent_tokens(augmented_messages):
            yield sse
            if is_error:
                # validation_task.cancel()  # disabled with search
                return
            full_reply += delta

        # valid_web = await validation_task        # disabled with search
        # valid_urls = {r["url"] for r in curated + valid_web}  # disabled with search
        # valid_citations = [c for c in citations if c["url"] in valid_urls]  # disabled with search

        stored_reply = _inject_citation_links(full_reply, citations) if citations else full_reply
        metadata = AIMessageMetadata(answer_incorrectly=req.answer_incorrectly).model_dump(exclude_none=True)
        _schedule_exchange_save(request.app.state.messages, user, conv_id, req.message, [stored_reply], assistant_metadata=metadata)

        yield _sse({"type": "done", "conversation_id": conv_id, "reply": stored_reply})

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
    system_instruction = _build_system_instruction(
        answer_incorrectly=req.answer_incorrectly,
        has_choices=len(req.answer_choices) > 0,
    )
    messages = _build_standard_messages(history, req.message, system_prompt=system_instruction)

    return StreamingResponse(
        _standard_stream(messages, col, user, conv_id, req.message, answer_incorrectly=req.answer_incorrectly),
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
