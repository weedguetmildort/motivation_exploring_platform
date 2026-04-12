# backend/app/services/knowledge_links.py
from typing import Optional, List
from datetime import datetime, timezone
from pymongo.collection import Collection
from bson import ObjectId

from ..schemas.knowledge_link import (
    KnowledgeLinkCreate,
    KnowledgeLinkUpdate,
    KnowledgeLinkPublic,
)

def get_knowledge_links_collection(db) -> Collection:
    return db["knowledge_links"]

def ensure_indexes(links: Collection) -> None:
    links.create_index("active")
    links.create_index("tags")
    links.create_index([("title", "text"), ("description", "text")])

def normalize_tags(tags: List[str]) -> List[str]:
    seen = set()
    cleaned = []

    for tag in tags:
        value = str(tag).strip().lower()
        if value and value not in seen:
            seen.add(value)
            cleaned.append(value)

    return cleaned

def _to_public(doc: dict) -> KnowledgeLinkPublic:
    return KnowledgeLinkPublic(
        id=str(doc["_id"]),
        title=doc["title"],
        url=doc["url"],
        tags=doc.get("tags", []),
        description=doc["description"],
        active=bool(doc.get("active", True)),
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
        "active": bool(data.active),
        "created_at": now,
        "updated_at": now,
    }

    res = links.insert_one(doc)
    doc["_id"] = res.inserted_id

    return _to_public(doc)

def list_knowledge_links(links: Collection) -> List[KnowledgeLinkPublic]:
    docs = links.find().sort("created_at", -1)
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
        "active": bool(data.active),
        "updated_at": datetime.now(timezone.utc),
    }

    links.update_one(
        {"_id": ObjectId(link_id)},
        {"$set": update_doc},
    )

    updated = links.find_one({"_id": ObjectId(link_id)})
    if not updated:
        return None

    return _to_public(updated)

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