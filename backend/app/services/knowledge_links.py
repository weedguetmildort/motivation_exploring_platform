# backend/app/services/knowledge_links.py
from typing import Optional, List
from datetime import datetime, timezone
from pymongo.collection import Collection
from bson import ObjectId

from ..schemas.knowledge_link import (
    KnowledgeLinkCreate,
    KnowledgeLinkUpdate,
    KnowledgeLinkPublic,
    ExplorePreview,
    LinkStatus,
)


def get_knowledge_links_collection(db) -> Collection:
    return db["knowledge_links"]


def ensure_indexes(links: Collection) -> None:
    links.create_index("active")
    links.create_index("tags")
    links.create_index("status")
    links.create_index([("tags", 1), ("status", 1)])
    links.create_index([("title", "text"), ("description", "text")])


def normalize_tags(tags: List[str]) -> List[str]:
    # Deduplicate case-insensitively but preserve original casing so that
    # stored tags match the PREDEFINED_TAGS used in discovery queries.
    seen: set = set()
    cleaned = []
    for tag in tags:
        value = str(tag).strip()
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            cleaned.append(value)
    return cleaned


def _to_public(doc: dict) -> KnowledgeLinkPublic:
    raw_status = doc.get("status", "READY")
    try:
        status = LinkStatus(raw_status)
    except ValueError:
        status = LinkStatus.READY

    return KnowledgeLinkPublic(
        id=str(doc["_id"]),
        title=doc["title"],
        url=doc["url"],
        tags=doc.get("tags", []),
        description=doc["description"],
        status=status,
        last_checked=doc.get("last_checked"),
        last_http_code=doc.get("last_http_code"),
        last_error_type=doc.get("last_error_type"),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


def create_knowledge_link(
    links: Collection,
    data: KnowledgeLinkCreate,
) -> KnowledgeLinkPublic:
    now = datetime.now(timezone.utc)
    doc = {
        "title": data.title.strip(),
        "url": str(data.url).strip(),
        "tags": normalize_tags(data.tags),
        "description": data.description.strip(),
        "status": "READY",
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    res = links.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _to_public(doc)


def list_knowledge_links(links: Collection) -> List[KnowledgeLinkPublic]:
    docs = links.find().sort("created_at", -1)
    return [_to_public(doc) for doc in docs]


def list_knowledge_links_by_status(
    links: Collection,
    status: Optional[str],
) -> List[KnowledgeLinkPublic]:
    if status is None:
        return list_knowledge_links(links)
    docs = links.find({"status": status}).sort("created_at", -1)
    return [_to_public(doc) for doc in docs]


def find_knowledge_link_by_id(links: Collection, link_id: str) -> Optional[dict]:
    if not ObjectId.is_valid(link_id):
        return None
    return links.find_one({"_id": ObjectId(link_id)})


def update_knowledge_link(
    links: Collection,
    link_id: str,
    data: KnowledgeLinkUpdate,
) -> Optional[KnowledgeLinkPublic]:
    if not ObjectId.is_valid(link_id):
        return None
    existing = links.find_one({"_id": ObjectId(link_id)})
    if not existing:
        return None
    update_doc = {
        "title": data.title.strip(),
        "url": str(data.url).strip(),
        "tags": normalize_tags(data.tags),
        "description": data.description.strip(),
        "updated_at": datetime.now(timezone.utc),
        # status is intentionally NOT updated here — managed by health jobs and approve/reject
    }
    links.update_one({"_id": ObjectId(link_id)}, {"$set": update_doc})
    updated = links.find_one({"_id": ObjectId(link_id)})
    return _to_public(updated) if updated else None


def delete_knowledge_link(
    links: Collection,
    link_id: str,
) -> Optional[KnowledgeLinkPublic]:
    if not ObjectId.is_valid(link_id):
        return None
    existing = links.find_one({"_id": ObjectId(link_id)})
    if not existing:
        return None
    links.delete_one({"_id": ObjectId(link_id)})
    return _to_public(existing)


def approve_link(links: Collection, link_id: str) -> Optional[KnowledgeLinkPublic]:
    """Move a NEEDS_REVIEW link to READY."""
    if not ObjectId.is_valid(link_id):
        return None
    doc = links.find_one({"_id": ObjectId(link_id), "status": "NEEDS_REVIEW"})
    if not doc:
        return None
    now = datetime.now(timezone.utc)
    links.update_one(
        {"_id": ObjectId(link_id)},
        {"$set": {"status": "READY", "active": True, "updated_at": now}},
    )
    updated = links.find_one({"_id": ObjectId(link_id)})
    return _to_public(updated) if updated else None


def reject_link(links: Collection, link_id: str) -> Optional[KnowledgeLinkPublic]:
    """Move a NEEDS_REVIEW or NOT_READY link to REJECTED (tombstone)."""
    if not ObjectId.is_valid(link_id):
        return None
    doc = links.find_one(
        {"_id": ObjectId(link_id), "status": {"$in": ["NEEDS_REVIEW", "NOT_READY"]}}
    )
    if not doc:
        return None
    now = datetime.now(timezone.utc)
    links.update_one(
        {"_id": ObjectId(link_id)},
        {"$set": {"status": "REJECTED", "active": False, "updated_at": now}},
    )
    updated = links.find_one({"_id": ObjectId(link_id)})
    return _to_public(updated) if updated else None


def explore_link(
    links: Collection,
    link_id: str,
    openai_client,
    allowlist_cache: set,
    timeout: int = 10,
) -> Optional[ExplorePreview]:
    """Fetch the link's live page and return a preview of what would change — nothing
    is written to the database.  The admin reviews the proposed title/description (and
    the raw article excerpt as an alternative) then calls apply_explore to commit.

    Returns None for REJECTED links or invalid IDs.
    """
    from .link_health import fetch_page_metadata, fetch_readable_content, summarize_page_content, is_relevant

    if not ObjectId.is_valid(link_id):
        return None
    doc = links.find_one({"_id": ObjectId(link_id)})
    if not doc or doc.get("status") == "REJECTED":
        return None

    url = doc.get("url", "")
    tag = doc["tags"][0] if doc.get("tags") else "Other"

    fetched_title, fetched_description, article_excerpt, http_code = fetch_page_metadata(url, timeout=timeout)

    # When meta description is missing (was generic/absent) try fetching the full
    # readable content via Jina Reader and summarizing it with the LLM.  This handles
    # JS-rendered sites like GeeksforGeeks where the raw HTML carries no article text.
    if not fetched_description:
        readable = fetch_readable_content(url, timeout=timeout)
        if readable:
            fetched_description = summarize_page_content(readable, fetched_title or url, openai_client)
            if not article_excerpt:
                article_excerpt = readable[:500]

    # Judge relevance using the best available content (meta desc preferred, excerpt
    # as fallback, existing description as last resort so we always get a verdict).
    judge_title = fetched_title or doc.get("title", "")
    judge_description = fetched_description or article_excerpt or doc.get("description", "")
    link_dict = {"url": url, "title": judge_title, "description": judge_description}
    relevant, relevance_reason = is_relevant(tag, link_dict, openai_client, allowlist_cache)

    return ExplorePreview(
        proposed_title=fetched_title,
        proposed_description=fetched_description,
        article_excerpt=article_excerpt,
        http_code=http_code,
        relevant=relevant,
        relevance_reason=relevance_reason,
    )


def apply_explore(
    links: Collection,
    link_id: str,
    new_title: str,
    new_description: str,
    openai_client,
    allowlist_cache: set,
) -> Optional[KnowledgeLinkPublic]:
    """Save the admin-confirmed title/description, re-run the relevance judge, apply
    the same status transitions as run_health_check, and return the updated document.

    Returns None for REJECTED links or invalid IDs.
    """
    from .link_health import is_relevant

    if not ObjectId.is_valid(link_id):
        return None
    doc = links.find_one({"_id": ObjectId(link_id)})
    if not doc or doc.get("status") == "REJECTED":
        return None

    url = doc.get("url", "")
    tag = doc["tags"][0] if doc.get("tags") else "Other"
    now = datetime.now(timezone.utc)

    title = new_title.strip()
    description = new_description.strip()

    link_dict = {"url": url, "title": title, "description": description}
    relevant, relevance_reason = is_relevant(tag, link_dict, openai_client, allowlist_cache)

    update: dict = {"title": title, "description": description, "last_checked": now, "updated_at": now}

    current_status = doc.get("status", "READY")
    if current_status == "READY" and not relevant:
        update["status"] = "NOT_READY"
        update["active"] = False
        update["last_error_type"] = relevance_reason
    elif current_status == "NOT_READY" and relevant:
        update["status"] = "NEEDS_REVIEW"
        update["last_error_type"] = None
    elif relevant:
        update["last_error_type"] = None
    else:
        update["last_error_type"] = relevance_reason

    links.update_one({"_id": ObjectId(link_id)}, {"$set": update})
    updated = links.find_one({"_id": ObjectId(link_id)})
    return _to_public(updated) if updated else None


def reload_knowledge_links_cache(links: Collection) -> list:
    """Return list of READY link dicts for use in app.state.knowledge_links."""
    return [
        {
            "id": str(doc["_id"]),
            "title": doc["title"],
            "url": doc["url"],
            "description": doc["description"],
        }
        for doc in links.find({"status": "READY"})
    ]
