import os
import re
import uuid
from ddgs import DDGS
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


def get_chat_response(messages: list[dict]) -> str:
    try:
        resp = _client.chat.completions.create(
            model=os.getenv("UF_OPENAI_API_MODEL"),
            messages=messages,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream AI request failed")

def embed_html_superscripts(answer_text: str, url_citations: list[dict]) -> tuple[str, list[dict]]:
    # Assign numbers
    url_to_num = {}
    sources = []
    for c in url_citations:
        url = c["url"]
        if url not in url_to_num:
            url_to_num[url] = len(url_to_num) + 1
            sources.append({"n": url_to_num[url], "title": c.get("title"), "url": url})

    # Prepare inserts
    inserts = []
    for c in url_citations:
        url = c["url"]
        n = url_to_num[url]
        end = c.get("end_index")
        if isinstance(end, int):
            inserts.append((end, f'<sup><a href="{url}" target="_blank" rel="noreferrer">{n}</a></sup>'))

    inserts.sort(key=lambda t: t[0], reverse=True)

    embedded = answer_text
    for idx, marker in inserts:
        if 0 <= idx <= len(embedded):
            embedded = embedded[:idx] + marker + embedded[idx:]

    return embedded, sources

def web_search(query: str, max_results: int = 5) -> list[dict]:
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))
    # Each result: {"title": str, "href": str, "body": str}


def get_chat_response_links(messages: list[dict]) -> dict[str, str | list]:
    try:
        # Extract the last user message as the search query
        query = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "",
        )

        # Always search DuckDuckGo — citations are core to this response type
        results = web_search(query)

        search_context = "\n\n".join(
            f"[{i+1}] {r['title']}\n{r['body']}\nURL: {r['href']}"
            for i, r in enumerate(results)
        )

        augmented_messages = [
            *messages[:-1],  # everything except the last user message
            {
                "role": "user",
                "content": (
                    f"{query}\n\n"
                    f"Use the following search results to answer. "
                    f"Cite sources by their number (e.g. [1], [2]):\n\n{search_context}"
                ),
            },
        ]

        reply = get_chat_response(augmented_messages)
        url_citations = [{"url": r["href"], "title": r["title"]} for r in results]
        embedded_reply, citations = embed_html_superscripts(reply, url_citations)
        return {"reply": embedded_reply, "citations": citations}

    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Upstream AI request failed: {e}")

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

    _save_message(request.app.state.messages, "user", user, conv_id, req.message)

    # Agent A: sees full prior conversation
    system_instruction = (
        "You are a helpful assistant who generates clear and concise answers "
        "to help students answer some quiz questions."
    )
    reply = get_chat_response([
        {"role": "system", "content": system_instruction},
        *history,
        {"role": "user", "content": req.message},
    ])

    # Agent B: sees full prior conversation plus Agent A's new response
    system_instruction_b = (
        "You are a helpful assistant who generates clear and concise answers "
        "to help students answer some quiz questions. "
        "Double check that the answers provided by [AGENT A] are correct, and if not, provide the correct answer."
    )
    second_reply = get_chat_response([
        {"role": "system", "content": system_instruction_b},
        *history,
        {"role": "user", "content": req.message},
        {"role": "assistant", "content": f"[AGENT A] {reply}"},
    ])

    # Insert both agent replies as a single assistant document
    _save_message(request.app.state.messages, "assistant", user, conv_id, [reply, second_reply])

    return ChatResponse(reply=[reply, second_reply], conversation_id=conv_id)


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
        "to help students answer some quiz questions."
        "Use web searches primarily to gather information and cite sources"
    )
    output = get_chat_response_links([
        {"role": "system", "content": system_instruction},
        *history,
        {"role": "user", "content": req.message},
    ])
    
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
