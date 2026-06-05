# backend/app/services/link_health.py
import asyncio
import os
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


# ── HTTP health check ────────────────────────────────────────────────────────

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
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})

            if resp.status_code == 404:
                return False, 404, "http_error"

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
) -> bool:
    """Single source of truth for link relevance. Hard allowlist filter first, then LLM."""
    if not domain_is_allowed(link.get("url", ""), allowlist_cache):
        return False
    return llm_judges_relevant(
        subject_tag,
        link.get("title", ""),
        link.get("description", ""),
        openai_client,
    )


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
        relevant = ok and is_relevant(tag, link, openai_client, allowlist_cache)

        update: dict = {"last_checked": now}

        if current_status == "READY":
            if not (ok and relevant):
                update["status"] = "NOT_READY"
                update["last_http_code"] = http_code
                update["last_error_type"] = error_type or ("irrelevant" if ok else error_type)
                degraded += 1
        else:  # NOT_READY
            if ok and relevant:
                update["status"] = "NEEDS_REVIEW"
                update["last_http_code"] = http_code
                update["last_error_type"] = None
                recovered += 1
            else:
                update["last_http_code"] = http_code
                update["last_error_type"] = error_type

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

    for tag in PREDEFINED_TAGS:
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
            if not is_relevant(tag, link_dict, openai_client, allowlist_cache):
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
