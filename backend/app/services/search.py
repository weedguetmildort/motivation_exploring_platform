"""Search agent service using NaviGator AI search endpoint + one-shot citation injection."""

import os
import re
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from openai import OpenAI

_UF_BASE_URL = os.getenv("UF_OPENAI_BASE_URL", "https://api.ai.it.ufl.edu")
_UF_API_KEY = os.getenv("UF_OPENAI_API_KEY")
_UF_SEARCH_TOOL = os.getenv("UF_SEARCH_TOOL_NAME", "litellm-search")


def _run_search(query: str, max_results: int = 5) -> list[dict]:
    """Execute a NaviGator AI search and return raw results.

    Returns [] on any failure so the caller can fall back to answering without search.
    """
    max_results = min(max_results, 10)
    try:
        resp = httpx.post(
            f"{_UF_BASE_URL}/v1/search/{_UF_SEARCH_TOOL}",
            headers={"Authorization": f"Bearer {_UF_API_KEY}", "Content-Type": "application/json"},
            json={"query": query, "max_results": max_results},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception:
        return []
    # Each result: {"title": str, "url": str, "snippet": str, "date": str, "last_updated": str}


def _check_url(url: str) -> tuple[str, bool]:
    """Validate a URL by streaming a GET (no body downloaded).

    Drops the URL if:
    - HTTP 404 status
    - Redirected to the site homepage (path vanished) — indicates the article
      was removed but the domain still exists (stale search index entries).

    Keeps the URL on any other response or error (paywalled, rate-limited, slow).
    """
    try:
        with httpx.stream(
            "GET", url,
            timeout=3.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as r:
            if r.status_code == 404:
                return url, False
            # Homepage redirect: original URL had a path, final URL is just the root
            original_path = urlparse(url).path.rstrip("/")
            final_path = urlparse(str(r.url)).path.rstrip("/")
            if original_path and not final_path:
                return url, False
            return url, True
    except Exception:
        return url, True  # Keep on error — don't penalise slow/protected URLs


def _filter_valid_urls(results: list[dict]) -> list[dict]:
    """Remove results whose URL definitively returns 404. Checks run in parallel."""
    if not results:
        return results
    with ThreadPoolExecutor(max_workers=len(results)) as pool:
        futures = {pool.submit(_check_url, r["url"]): r for r in results}
        valid_urls = {
            url
            for f in as_completed(futures)
            for url, ok in [f.result()]
            if ok
        }
    return [r for r in results if r["url"] in valid_urls]


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
        text = re.sub(
            r"\[([^\]\[]+)\]\[" + n + r"\]",
            lambda m, u=url: f"[{m.group(1)}]({u})",
            text,
        )
        # Fallback: bare [N] → [N](url)
        text = re.sub(r"\[" + n + r"\](?!\()", f"[{n}]({url})", text)
    return text


def get_chat_response_with_search(
    client: OpenAI,
    model: str,
    messages: list[dict],
) -> dict[str, str | list]:
    """One-shot search: search once, validate URLs, inject results as context,
    one LLM call, then replace citation markers with real URLs deterministically.

    Returns:
        {"reply": str, "citations": list[{"n": int, "title": str, "url": str}]}
    """
    query = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )

    results = _run_search(query)
    results = _filter_valid_urls(results)

    if not results:
        resp = client.chat.completions.create(model=model, messages=messages)
        return {"reply": (resp.choices[0].message.content or "").strip(), "citations": []}

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
        "Do not write out URLs, do not add a References or Sources section."
    )

    system = next((m for m in messages if m["role"] == "system"), None)
    if system:
        patched_messages = [
            {**system, "content": system["content"] + citation_instruction},
            *[m for m in messages if m["role"] != "system"],
        ]
    else:
        patched_messages = [
            {"role": "system", "content": citation_instruction.strip()},
            *messages,
        ]

    augmented = list(patched_messages)
    last_user_idx = next(
        i for i in reversed(range(len(augmented))) if augmented[i]["role"] == "user"
    )
    augmented[last_user_idx] = {
        **augmented[last_user_idx],
        "content": (
            augmented[last_user_idx]["content"]
            + NL + NL + "Search results:" + NL
            + search_context
        ),
    }

    resp = client.chat.completions.create(model=model, messages=augmented)
    reply_text = (resp.choices[0].message.content or "").strip()

    citations = [
        {"n": i + 1, "title": r["title"], "url": r["url"]}
        for i, r in enumerate(results)
    ]

    reply_text = _inject_citation_links(reply_text, citations)

    return {"reply": reply_text, "citations": citations}
