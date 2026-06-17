# backend/app/services/link_health.py
import asyncio
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
from openai import OpenAI

from .allowlist import domain_is_allowed, load_allowlist_cache

PREDEFINED_TAGS = [
    "Statistical Inference & Descriptive Statistics",
    "Conditional Probability",
    "Combinatorics & Counting",
    "Basic Probability",
    "Other",
]

# "Other" is a catch-all fallback for untagged links (see is_relevant below),
# not a real subject — searching for it during discovery returns junk.
DISCOVERABLE_TAGS = [tag for tag in PREDEFINED_TAGS if tag != "Other"]


# ── HTTP health check ────────────────────────────────────────────────────────

# A realistic browser fingerprint. Sites guarded by anti-bot/WAF services (Cloudflare,
# Akamai, etc.) often block bare "Mozilla/5.0" requests with 401/402/403 even though
# the page is genuinely live and accessible to a real browser.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Status codes that commonly indicate an anti-bot/WAF block rather than a genuinely
# dead or restricted page — treat as reachable so a real block doesn't get conflated
# with a removed page.
_BOT_BLOCK_STATUS_CODES = {401, 402, 403}

_RE_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_WHITESPACE = re.compile(r"\s+")
_RE_PARA = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)

# Content-area wrappers tried in order before falling back to the full page.
_CONTENT_AREA_PATTERNS = [
    re.compile(r"<article\b[^>]*>(.*?)</article>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<main\b[^>]*>(.*?)</main>", re.IGNORECASE | re.DOTALL),
    re.compile(
        r'<div\b[^>]*\bclass=["\'][^"\']*(?:content|article|post|entry|body)[^"\']*["\'][^>]*>(.*?)</div>',
        re.IGNORECASE | re.DOTALL,
    ),
]

# Lowercase substrings that identify known generic site-wide meta descriptions.
# These are useless for relevance judging and should be discarded so the system
# falls through to the article excerpt or URL slug instead.
_GENERIC_DESCRIPTION_FRAGMENTS = [
    "your all-in-one learning portal",          # GeeksforGeeks
    "a free, collaborative, example repository", # Rosetta Code
]


def _is_generic_description(desc: str) -> bool:
    """Return True when desc is a known site-wide boilerplate rather than page-specific content."""
    lower = desc.lower()
    return any(frag in lower for frag in _GENERIC_DESCRIPTION_FRAGMENTS)


def _url_slug_description(url: str) -> str:
    """Humanize the last meaningful path segment of a URL into a readable string.

    e.g. '.../introduction-to-divide-and-conquer-algorithm/' → 'Introduction To Divide And Conquer Algorithm'
    Falls back to '' when no useful segment is found.
    """
    path = urlparse(url).path
    segments = [s for s in path.rstrip("/").split("/") if s]
    if not segments:
        return ""
    slug = segments[-1]
    # Skip overly-generic trailing segments
    if slug in {"index", "home", "page", "article", "post", "blog", "dsa", "maths"}:
        slug = segments[-2] if len(segments) >= 2 else ""
    if not slug:
        return ""
    text = re.sub(r"[-_]+", " ", slug).strip()
    text = _RE_WHITESPACE.sub(" ", text)
    return text.title()


def _meta_content(html: str, attr: str, value: str) -> str:
    """Return the content= of the first <meta> tag that has attr=value (either attribute order)."""
    # attr=value before content=
    m = re.search(
        r"<meta\b[^>]*\b" + re.escape(attr) + r"\s*=\s*[\"']" + re.escape(value) + r"[\"'][^>]*\bcontent\s*=\s*[\"']([^\"'<>]*)[\"']",
        html, re.IGNORECASE,
    )
    if m:
        return m.group(1)
    # content= before attr=value
    m = re.search(
        r"<meta\b[^>]*\bcontent\s*=\s*[\"']([^\"'<>]*)[\"'][^>]*\b" + re.escape(attr) + r"\s*=\s*[\"']" + re.escape(value) + r"[\"']",
        html, re.IGNORECASE,
    )
    return m.group(1) if m else ""


def _first_article_paragraph(html: str, min_length: int = 80) -> str:
    """Return the first meaningful <p> text from a semantic content area.

    Tries <article>, <main>, and common content div classes in order, then falls back
    to the full page. Strips tags, collapses whitespace, and caps at 500 chars.
    min_length filters out nav items, captions, and other short inline text.
    """
    region = html
    for pattern in _CONTENT_AREA_PATTERNS:
        m = pattern.search(html)
        if m:
            region = m.group(1)
            break

    for p_match in _RE_PARA.finditer(region):
        text = _RE_HTML_TAG.sub("", p_match.group(1))
        text = _RE_WHITESPACE.sub(" ", text).strip()
        if len(text) >= min_length:
            return text[:500]
    return ""


def fetch_page_metadata(
    url: str,
    timeout: int = 10,
) -> tuple[str, str, str, Optional[int]]:
    """Fetch url and extract (title, description, article_excerpt, http_code).

    description  — best meta tag description (og:description or meta name=description)
    article_excerpt — first meaningful paragraph from article/main body content;
                      useful as a fallback when the meta description is generic.
    Returns ("", "", "", http_code) when unreachable or non-HTML.
    Bot-blocked responses (401/402/403) return empty strings without parsing.
    """
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=_BROWSER_HEADERS)
        http_code = resp.status_code
        if resp.status_code != 200:
            return "", "", "", http_code
        if "html" not in resp.headers.get("content-type", "").lower():
            return "", "", "", http_code
        html = resp.text[:51200]  # first 50 KB — meta tags and article intros are in <head>/<body>
    except Exception:
        return "", "", "", None

    _title_m = _RE_TITLE_TAG.search(html)
    title = (
        _meta_content(html, "property", "og:title")
        or _meta_content(html, "name", "title")
        or (_title_m.group(1).strip() if _title_m else "")
    )
    description = (
        _meta_content(html, "property", "og:description")
        or _meta_content(html, "name", "description")
    )
    # Discard site-wide boilerplate so callers fall through to a more useful signal.
    if _is_generic_description(description):
        description = ""
    excerpt = _first_article_paragraph(html)
    # When JS rendering hides the article body, derive a content hint from the URL slug
    # so the relevance judge and admin always have something meaningful to work with.
    if not excerpt:
        excerpt = _url_slug_description(url)
    return title.strip(), description.strip(), excerpt, http_code


def fetch_with_retries(
    url: str,
    max_retries: int = 3,
    timeout: int = 10,
) -> tuple[bool, Optional[int], Optional[str]]:
    """Check if a URL is reachable. Returns (ok, http_code, error_type).

    error_type values: "http_error", "redirect_root", "timeout", "connection_error"
    Returns (True, None, None) on protected/unknown errors to avoid penalizing them.
    """
    last_exc = None
    delays = [1, 2, 4]

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.get(url, headers=_BROWSER_HEADERS)

            if resp.status_code == 404:
                return False, 404, "http_error"

            if resp.status_code in _BOT_BLOCK_STATUS_CODES:
                return True, resp.status_code, None

            if resp.status_code >= 400:
                return False, resp.status_code, "http_error"

            # Detect redirect to site root (page removed)
            original_path = urlparse(url).path.rstrip("/")
            final_path = urlparse(str(resp.url)).path.rstrip("/")
            if original_path and not final_path:
                return False, resp.status_code, "redirect_root"

            return True, resp.status_code, None

        except httpx.TimeoutException:
            last_exc = "timeout"
        except httpx.ConnectError:
            last_exc = "connection_error"
        except Exception:
            # Unknown error — fail open (don't penalize protected/slow sites)
            return True, None, None

        if attempt < max_retries - 1:
            time.sleep(delays[min(attempt, len(delays) - 1)])

    # All retries exhausted
    if last_exc == "timeout":
        return False, None, "timeout"
    return False, None, "connection_error"


# ── LLM relevance judge ──────────────────────────────────────────────────────

def llm_judges_relevant(
    subject_tag: str,
    title: str,
    description: str,
    openai_client: OpenAI,
) -> bool:
    """Ask the LLM if the link is relevant to the subject. Fails open (returns True on error)."""
    try:
        prompt = (
            f"You are evaluating whether a web resource is relevant to the subject '{subject_tag}'. "
            f"Resource title: '{title}'. Description: '{description}'. "
            "Reply with only YES or NO."
        )
        model = os.getenv("UF_OPENAI_API_MODEL", "gpt-4o-mini")
        resp = openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0,
        )
        answer = (resp.choices[0].message.content or "").strip().upper()
        return answer.startswith("YES")
    except Exception as e:
        print(f"[link_health] llm_judges_relevant error: {e}")
        return True  # fail open


def is_relevant(
    subject_tag: str,
    link: dict,
    openai_client: OpenAI,
    allowlist_cache: set,
) -> tuple[bool, Optional[str]]:
    """Single source of truth for link relevance. Hard allowlist filter first, then LLM.

    Returns (is_relevant, reason). reason is None when relevant, otherwise one of:
      "domain_not_allowed" — domain isn't in the trusted allowlist (hard filter; LLM not consulted)
      "irrelevant"         — domain is trusted but the LLM judged the content off-topic
    """
    if not domain_is_allowed(link.get("url", ""), allowlist_cache):
        return False, "domain_not_allowed"
    if llm_judges_relevant(
        subject_tag,
        link.get("title", ""),
        link.get("description", ""),
        openai_client,
    ):
        return True, None
    return False, "irrelevant"


# ── Health checker (Job 1) ───────────────────────────────────────────────────

def run_health_check(db, settings, openai_client: OpenAI, allowlist_cache: set) -> dict:
    """Validate all READY and NOT_READY links. Update status based on results.

    Transitions:
      READY + fail → NOT_READY
      NOT_READY + pass → NEEDS_REVIEW  (admin must confirm before READY)
    """
    from .knowledge_links import get_knowledge_links_collection

    col = get_knowledge_links_collection(db)
    links = list(col.find({"status": {"$in": ["READY", "NOT_READY"]}}))

    checked = degraded = recovered = 0
    now = datetime.now(timezone.utc)

    for link in links:
        link_id = link["_id"]
        url = link.get("url", "")
        current_status = link.get("status", "READY")
        tag = link["tags"][0] if link.get("tags") else "Other"

        ok, http_code, error_type = fetch_with_retries(
            url,
            max_retries=settings.MAX_RETRIES_LINK_CHECK,
            timeout=settings.LINK_REQUEST_TIMEOUT,
        )

        # Only consult the relevance gate when the page is reachable — short-circuits
        # the allowlist/LLM checks for dead links (matches prior `ok and is_relevant(...)`).
        relevant, relevance_reason = (
            is_relevant(tag, link, openai_client, allowlist_cache) if ok else (False, None)
        )
        # Reachability errors (http_error/timeout/...) take priority for diagnostics;
        # otherwise surface *why* it's not relevant — "domain_not_allowed" (untrusted
        # source) vs "irrelevant" (LLM judged the content off-topic) — instead of a
        # single generic label that hides which gate actually blocked the link.
        fail_reason = error_type or relevance_reason

        update: dict = {"last_checked": now}

        if current_status == "READY":
            if not (ok and relevant):
                update["status"] = "NOT_READY"
                update["last_http_code"] = http_code
                update["last_error_type"] = fail_reason
                degraded += 1
        else:  # NOT_READY
            if ok and relevant:
                update["status"] = "NEEDS_REVIEW"
                update["last_http_code"] = http_code
                update["last_error_type"] = None
                recovered += 1
            else:
                update["last_http_code"] = http_code
                update["last_error_type"] = fail_reason

        col.update_one({"_id": link_id}, {"$set": update})
        checked += 1

    print(f"[link_health] health_check done: checked={checked} degraded={degraded} recovered={recovered}")
    return {"checked": checked, "degraded": degraded, "recovered": recovered}


# ── Discovery (Job 2) ────────────────────────────────────────────────────────

async def _search_for_tag(tag: str) -> list[dict]:
    """Async wrapper around the UF NaviGator search API."""
    from .search import _run_search
    return await _run_search(tag, max_results=3)


def run_discovery(db, settings, openai_client: OpenAI, allowlist_cache: set) -> dict:
    """Search for new links for subject tags below MAX_LIVE_LINKS_PER_SUBJECT.

    Discovered links are inserted as NEEDS_REVIEW.
    """
    from .knowledge_links import get_knowledge_links_collection

    col = get_knowledge_links_collection(db)
    discovered = 0
    now = datetime.now(timezone.utc)

    for tag in DISCOVERABLE_TAGS:
        live_count = col.count_documents({"tags": tag, "status": "READY"})
        if live_count >= settings.MAX_LIVE_LINKS_PER_SUBJECT:
            continue

        # Fetch candidates via web search
        try:
            results = asyncio.run(_search_for_tag(tag))
        except Exception as e:
            print(f"[link_health] discovery search failed for tag '{tag}': {e}")
            continue

        added_this_tag = 0
        for candidate in results:
            if added_this_tag >= settings.CANDIDATES_PER_CYCLE:
                break

            url = candidate.get("url", "").strip()
            title = candidate.get("title", "").strip()
            description = candidate.get("snippet", "").strip()

            if not url or not title:
                continue

            # Hard credibility filter
            if not domain_is_allowed(url, allowlist_cache):
                continue

            # Dedupe: skip if this URL already exists for this tag in any status
            if col.find_one({"url": url, "tags": tag}):
                continue

            # Fetch health check
            ok, http_code, error_type = fetch_with_retries(
                url,
                max_retries=settings.MAX_RETRIES_LINK_CHECK,
                timeout=settings.LINK_REQUEST_TIMEOUT,
            )
            if not ok:
                continue

            # Relevance check
            link_dict = {"url": url, "title": title, "description": description}
            relevant, _ = is_relevant(tag, link_dict, openai_client, allowlist_cache)
            if not relevant:
                continue

            # Insert as NEEDS_REVIEW
            doc = {
                "title": title,
                "url": url,
                "tags": [tag],
                "description": description,
                "status": "NEEDS_REVIEW",
                "active": False,
                "source": "discovery",
                "discovered_at": now,
                "last_checked": now,
                "last_http_code": http_code,
                "last_error_type": None,
                "created_at": now,
                "updated_at": now,
            }
            col.insert_one(doc)
            discovered += 1
            added_this_tag += 1
            print(f"[link_health] discovered candidate for '{tag}': {url}")

    print(f"[link_health] discovery done: discovered={discovered}")
    return {"discovered": discovered}
