import os
import re
import httpx
import asyncio
from urllib.parse import urlparse
from openai import AsyncOpenAI

_UF_BASE_URL = os.getenv("UF_OPENAI_BASE_URL", "https://api.ai.it.ufl.edu")
_UF_API_KEY = os.getenv("UF_OPENAI_API_KEY")
_UF_SEARCH_TOOL = os.getenv("UF_SEARCH_TOOL_NAME", "")


async def _run_search(query: str, max_results: int = 5) -> list[dict]:
    """Execute a NaviGator AI search asynchronously and return raw results.

    Returns [] on any failure so the caller can fall back to answering without search.
    If UF_SEARCH_TOOL_NAME is set, passes it in the URL path. Otherwise falls back
    to passing the chat model name as the 'model' body parameter.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            body: dict = {"query": query, "max_results": max_results}
            if _UF_SEARCH_TOOL:
                url = f"{_UF_BASE_URL}/v1/search/{_UF_SEARCH_TOOL}"
            else:
                url = f"{_UF_BASE_URL}/v1/search"
                body["model"] = os.getenv("UF_OPENAI_API_MODEL", "")
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {_UF_API_KEY}", "Content-Type": "application/json"},
                json=body,
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

    Runs checks concurrently so even slow URLs are validated without serialising
    the wait. Intended to run as a background task concurrent with token streaming.
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

    Pure function — no I/O. Returns (augmented_messages, citations) or
    (messages, []) if results is empty.
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

    # Alternative citation instruction (more detailed, kept for reference):
    # citation_instruction = (
    #     NL + NL
    #     + "When you write a sentence that is supported by a search result, cite it by writing the "
    #     "first key noun or short phrase (1–4 words) in that sentence as [phrase][N], "
    #     "where N is the source number. Write the marker as you write the word — inline, not at the end. "
    #     "Never append a citation after the sentence ends. Never use equations or formulas as the phrase. "
    #     "Example: 'The [probability][1] of rolling a 6 is 1/6.' "
    #     "Example: '[Mitosis][1] involves four distinct phases.' "
    #     "Do not write out URLs. Do not add a references section or citations list."
    #     "Write in-line citations for the first key noun or short phrase that matches the topic or content of the search result."
    #     "Format the citation marker as [key phrase][N], where N corresponds to the numbered search result. Place the marker immediately after the key phrase, not at the end of the sentence. "
    #     "Do not use equations or formulas as key phrases. "
    #     "Do not add extra phrases just to fit in a citation. Use the closest word or phrase that exists naturally in the sentence. "
    #     "Do not format the citations as footnotes."
    #     "For example, when citing a search result about probability, key phrases to wrap might be 'probability', 'fair dice', 'outcomes', 'Baye's Theorem', 'addition rule', 'independent events,' etc."
    #     "Another example: When citing a search result about mitosis, key phrases to wrap might be 'mitosis', 'cell division', 'prophase', 'metaphase', 'anaphase', 'telophase', etc. "
    #     "Do not add a separate references section or list of citations at the end of your response. "
    # )
    citation_instruction = (
        NL + NL
        + "Cite sources by wrapping the first phrase that supports each fact in a reference-style link: "
        "[key phrase][N] where N is the source number. "
        "Place it immediately around the first words the source supports or that match the general topic that the sources cover. "
        "Do not use equations or formulas as key phrases. "
        "Do not add extra phrases just to fit in a citation. Use the closest word or phrase that exists naturally in the sentence. "
        "Do not write out URLs, do not add a References or Sources section, "
        "do not add a citations list at the end under any circumstances."
        "Example: '[Mitosis][1] involves [four distinct phases][2] and requires [spindle fibers][3].' "
        "Example: The [probability][1] of rolling a 6 on a [fair die][2] is 1/6. "
        "Example: The [Eiffel Tower][1] is located in Paris. "
        "Example: The [chemical decomposition of hydrogen peroxide][1] produces water and oxygen. "
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


_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "be", "as", "it",
    "its", "this", "that", "how", "what", "when", "where", "why", "which",
    "about", "into", "than", "more", "also", "has", "have", "had",
})

_RE_UNLINKED_PREFIX = r"(?<!\[)(?<!\()\b"
_RE_UNLINKED_SUFFIX = r"\b(?!\])"
_RE_FORMULA_CHARS = re.compile(r"[=÷×≥≤≠→←+\-*/\\|^]")


def _title_keywords(title: str) -> list[str]:
    """Extract candidate keywords from a result title, longest first."""
    words = re.split(r"[\s\-\u2013\u2014|:/,.()\[\]]+", title)
    candidates = [w for w in words if len(w) >= 4 and w.lower() not in _STOP_WORDS]
    return sorted(candidates, key=len, reverse=True)


def _unlinked_search(term: str, text: str) -> re.Match | None:
    """Find the first occurrence of term in text that is not already inside a markdown link."""
    return re.search(
        _RE_UNLINKED_PREFIX + re.escape(term) + _RE_UNLINKED_SUFFIX,
        text, re.IGNORECASE,
    )


def _place_marker_inline(phrase: str, url: str, before_marker: str, after_marker: str) -> str:
    """Try to place a citation link for phrase inside before_marker.

    Tries the exact phrase first, then progressively shorter contiguous
    sub-phrases (longest first, stop-words and short tokens skipped).
    Falls back to in-place conversion if nothing matches.
    """
    if not _RE_FORMULA_CHARS.search(phrase):
        exact = _unlinked_search(phrase, before_marker)
        if exact:
            word = before_marker[exact.start():exact.end()]
            return before_marker[:exact.start()] + f"[{word}]({url})" + before_marker[exact.end():] + after_marker

    words = phrase.split()
    for length in range(len(words) - 1, 0, -1):
        for start in range(len(words) - length + 1):
            sub = " ".join(words[start:start + length])
            if sub.lower() in _STOP_WORDS or len(sub) < 4 or _RE_FORMULA_CHARS.search(sub):
                continue
            sub_match = _unlinked_search(sub, before_marker)
            if sub_match:
                word = before_marker[sub_match.start():sub_match.end()]
                return (
                    before_marker[:sub_match.start()]
                    + f"[{word}]({url})"
                    + before_marker[sub_match.end():]
                    + after_marker
                )

    return before_marker + f"[{phrase}]({url})" + after_marker


def _inject_citation_links(text: str, citations: list[dict]) -> str:
    """Replace citation markers in the model's reply with markdown links.

    Strategy 1 — model used [phrase][N]:
      Find the phrase before the marker; if found link it there and drop the
      marker. If not found exactly, try shorter sub-phrases. Falls back to
      converting the marker in place.
    Strategy 2 — model used bare [N]: convert to [N](url).
    Strategy 3 — no marker: keyword-match against the result title.
    """
    for c in citations:
        url = c["url"]
        n = str(c["n"])

        marker_match = re.search(r"\[([^\]\[]+)\]\s*\[" + n + r"\]", text)
        if marker_match:
            text = _place_marker_inline(
                marker_match.group(1), url,
                text[:marker_match.start()],
                text[marker_match.end():],
            )
            continue

        new_text = re.sub(r"\[" + n + r"\](?!\()", f"[{n}]({url})", text)
        if new_text != text:
            text = new_text
            continue

        for kw in _title_keywords(c["title"]):
            kw_match = _unlinked_search(kw, text)
            if kw_match:
                word = text[kw_match.start():kw_match.end()]
                text = text[:kw_match.start()] + f"[{word}]({url})" + text[kw_match.end():]
                break

    return text


async def get_chat_response_with_search(
    client: AsyncOpenAI,
    model: str,
    messages: list[dict],
    db_links: list[dict] | None = None,
) -> dict[str, str | list]:
    """One-shot search: search, validate URLs, inject context, one LLM call.

    Returns:
        {"reply": str, "citations": list[{"n": int, "title": str, "url": str}]}
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
    augmented, citations = _build_search_context(messages, curated + valid_web)

    resp = await client.chat.completions.create(model=model, messages=augmented)
    reply_text = (resp.choices[0].message.content or "").strip()
    reply_text = _inject_citation_links(reply_text, citations) if citations else reply_text

    return {"reply": reply_text, "citations": citations}
