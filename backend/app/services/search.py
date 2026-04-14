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
    Sub-page URLs (e.g. khanacademy.com/page) are returned as-is from the search API
    — this function does not restrict results to root domains.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_UF_BASE_URL}/v1/search/{_UF_SEARCH_TOOL}",
                headers={"Authorization": f"Bearer {_UF_API_KEY}", "Content-Type": "application/json"},
                json={"query": query, "max_results": max_results},
            )
            if not resp.is_success:
                print(f"[search] _run_search HTTP {resp.status_code} body: {resp.text[:500]}")
            resp.raise_for_status()
            results = resp.json().get("results", [])
            print(f"[search] _run_search: query={query!r} returned {len(results)} result(s)")
            return results
    except Exception as e:
        print(f"[search] _run_search failed: {type(e).__name__}: {e}")
        return []


async def _check_url(url: str, client: httpx.AsyncClient) -> tuple[str, bool]:
    """Validate a URL asynchronously.

    Drops the URL if:
    - HTTP 404 status
    - Redirected to the site homepage (path vanished)
    Keeps the URL on any other response or error.

    Sub-page URLs (e.g. khanacademy.com/algebra) are kept as long as they do not
    redirect to the root domain — this preserves specific resource pages.
    """
    try:
        async with client.stream(
            "GET", url,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as r:
            if r.status_code == 404:
                return url, False

            # Drop URLs that redirect from a specific path to the site root —
            # this means the specific page no longer exists.
            original_path = urlparse(url).path.rstrip("/")
            final_path = urlparse(str(r.url)).path.rstrip("/")
            if original_path and not final_path:
                return url, False
            return url, True
    except Exception:
        return url, True  # Keep on error — don't penalise slow/protected URLs


async def _filter_valid_urls(results: list[dict]) -> list[dict]:
    """Remove results whose URL definitively returns 404 or redirects to a homepage.

    Runs checks concurrently (15s client timeout) so even slow URLs are validated
    without serialising the wait. Intended to run as a background asyncio.Task
    concurrent with token streaming so the full 15s is never felt as blocking latency.
    """
    if not results:
        return results

    async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
        tasks = [_check_url(r["url"], client) for r in results]
        checked_urls = await asyncio.gather(*tasks)

    valid_urls = {url for url, is_valid in checked_urls if is_valid}
    filtered = [r for r in results if r["url"] in valid_urls]
    dropped = len(results) - len(filtered)
    if dropped:
        print(f"[search] _filter_valid_urls: dropped {dropped} of {len(results)} URL(s)")
    return filtered


def _build_search_context(
    messages: list[dict],
    results: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Build the augmented message list and citation map from assembled results.

    Pure function — no I/O. Accepts an already-assembled result list so callers
    can control validation independently (e.g. run it as a background task concurrent
    with token streaming).

    Returns (augmented_messages, citations) or (messages, []) if results is empty.
    citations format: [{"n": int, "title": str, "url": str}]
    """
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
        + "Cite sources by wrapping the first phrase that supports each fact in a reference-style link: "
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


async def prepare_search_messages(
    messages: list[dict],
    db_links: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Run search + URL validation, build augmented message list, return (augmented_messages, citations).

    Convenience wrapper used by get_chat_response_with_search. For streaming endpoints
    that need URL validation to run concurrently with token output, use _run_search,
    _filter_valid_urls, and _build_search_context directly.
    """
    query = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )

    raw_web = await _run_search(query)
    valid_web = await _filter_valid_urls(raw_web)

    curated = [
        {"title": l.get("title", ""), "url": l.get("url", ""), "snippet": l.get("description", "")}
        for l in (db_links or [])
        if l.get("url")
    ]
    return _build_search_context(messages, curated + valid_web)


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
