import os
import re
import httpx
import asyncio
from urllib.parse import urlparse
from openai import AsyncOpenAI

_UF_BASE_URL = os.getenv("UF_OPENAI_BASE_URL", "https://api.ai.it.ufl.edu")
_UF_API_KEY = os.getenv("UF_OPENAI_API_KEY")
_UF_SEARCH_TOOL = os.getenv("UF_SEARCH_TOOL_NAME", "litellm-search")


async def _run_search(query: str, max_results: int = 5) -> list[dict]:
    """Execute a NaviGator AI search asynchronously and return raw results.

    Returns [] on any failure so the caller can fall back to answering without search.
    """
    try:
        # Use AsyncClient to prevent blocking the FastAPI event loop
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_UF_BASE_URL}/v1/search/{_UF_SEARCH_TOOL}",
                headers={"Authorization": f"Bearer {_UF_API_KEY}", "Content-Type": "application/json"},
                json={"query": query, "max_results": max_results},
            )
            resp.raise_for_status()
            return resp.json().get("results", [])
    except Exception:
        return []


async def _check_url(url: str, client: httpx.AsyncClient) -> tuple[str, bool]:
    """Validate a URL asynchronously.

    Drops the URL if:
    - HTTP 404 status
    - Redirected to the site homepage (path vanished)
    Keeps the URL on any other response or error.
    """
    try:
        # Stream the GET request asynchronously (no body downloaded)
        async with client.stream(
            "GET", url,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as r:
            if r.status_code == 404:
                return url, False
            
            # Homepage redirect check
            original_path = urlparse(url).path.rstrip("/")
            final_path = urlparse(str(r.url)).path.rstrip("/")
            if original_path and not final_path:
                return url, False
            return url, True
    except Exception:
        return url, True  # Keep on error — don't penalise slow/protected URLs


async def _filter_valid_urls(results: list[dict]) -> list[dict]:
    """Remove results whose URL definitively returns 404. Checks run concurrently via asyncio."""
    if not results:
        return results

    # Share a single AsyncClient for all concurrent checks to save connection overhead
    async with httpx.AsyncClient(timeout=3.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
        # Create a list of background tasks for checking URLs
        tasks = [_check_url(r["url"], client) for r in results]
        
        # Await them all simultaneously
        checked_urls = await asyncio.gather(*tasks)

    # Filter into a set of valid URLs
    valid_urls = {url for url, is_valid in checked_urls if is_valid}
    return [r for r in results if r["url"] in valid_urls]


async def prepare_search_messages(
    messages: list[dict],
    db_links: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Run search, build augmented message list, return (augmented_messages, citations).

    citations format: [{"n": int, "title": str, "url": str}]
    Returns (original messages, []) if search yields no results — caller should
    fall back to a plain LLM call in that case.
    """
    query = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )

    results = await _run_search(query)
    results = await _filter_valid_urls(results)

    curated = [
        {"title": l["title"], "url": l["url"], "snippet": l["description"]}
        for l in (db_links or [])
    ]
    results = curated + results

    if not results:
        return messages, []

    NL = chr(10)
    context_lines = []
    for i, r in enumerate(results):
        context_lines.append("[" + str(i + 1) + "] " + r["title"])
        context_lines.append("URL: " + r["url"])
        context_lines.append(r["snippet"])
        context_lines.append("")
    search_context = NL.join(context_lines)

    citation_instruction = (
        NL + NL
        + "Cite sources by wrapping the key phrase that supports each fact in a reference-style link: "
        "[key phrase][N] where N is the source number. "
        "Place it immediately around the words the source supports. "
        "Example: 'Mitosis involves [four distinct phases][1] and requires [spindle fibers][2].' "
        "Do not write out URLs, do not add a References or Sources section, "
        "do not add a citations list at the end under any circumstances."
    )

    system = next((m for m in messages if m["role"] == "system"), None)
    if system:
        patched = [
            {**system, "content": system["content"] + citation_instruction},
            *[m for m in messages if m["role"] != "system"],
        ]
    else:
        patched = [{"role": "system", "content": citation_instruction.strip()}, *messages]

    augmented = list(patched)
    last_user_idx = next(
        i for i in reversed(range(len(augmented))) if augmented[i]["role"] == "user"
    )
    augmented[last_user_idx] = {
        **augmented[last_user_idx],
        "content": augmented[last_user_idx]["content"] + NL + NL + "Search results:" + NL + search_context,
    }

    citations = [{"n": i + 1, "title": r["title"], "url": r["url"]} for i, r in enumerate(results)]
    return augmented, citations


def _inject_citation_links(text: str, citations: list[dict]) -> str:
    """Replace citation markers in the model's reply with markdown links.

    Primary pattern:  [key phrase][N] → [key phrase](url)
    Fallback pattern: [N]            → [N](url)

    URLs are injected deterministically — the model never writes them directly,
    so they cannot be hallucinated or mangled.
    """
    for c in citations:
        url = c["url"]
        n = str(c["n"])
        # Primary: [key phrase][N] → [key phrase](url)
        # \s* between the brackets tolerates any whitespace the model may insert
        text = re.sub(
            r"\[([^\]\[]+)\]\s*\[" + n + r"\]",
            lambda m, u=url: f"[{m.group(1)}]({u})",
            text,
        )
        # Fallback: bare [N] → [N](url)
        text = re.sub(r"\[" + n + r"\](?!\()", f"[{n}]({url})", text)
    return text


async def get_chat_response_with_search(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict],
    db_links: list[dict] | None = None,
) -> dict[str, str | list]:
    """One-shot search: search once, validate URLs, inject results as context,
    one LLM call, then replace citation markers with real URLs deterministically.

    Returns:
        {"reply": str, "citations": list[{"n": int, "title": str, "url": str}]}
    """
    augmented, citations = await prepare_search_messages(messages, db_links)

    if not citations:
        resp = await client.chat.completions.create(model=model, messages=augmented)
        return {"reply": (resp.choices[0].message.content or "").strip(), "citations": []}

    resp = await client.chat.completions.create(model=model, messages=augmented)
    reply_text = (resp.choices[0].message.content or "").strip()
    reply_text = _inject_citation_links(reply_text, citations)

    return {"reply": reply_text, "citations": citations}
