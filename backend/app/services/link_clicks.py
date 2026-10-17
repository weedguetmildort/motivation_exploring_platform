# backend/app/services/link_clicks.py
from typing import Optional, List
from datetime import datetime, timezone
from pymongo.collection import Collection

from ..schemas.link_click import LinkClickCreate, LinkClickPublic


def get_link_clicks_collection(db) -> Collection:
    return db["link_clicks"]


def ensure_indexes(col: Collection) -> None:
    col.create_index("user_id")
    col.create_index("conversation_id")
    col.create_index([("clicked_at", -1)])


def _to_public(doc: dict) -> LinkClickPublic:
    return LinkClickPublic(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        user_email=doc["user_email"],
        quiz_id=doc.get("quiz_id"),
        question_id=doc.get("question_id"),
        conversation_id=doc.get("conversation_id"),
        url=doc["url"],
        clicked_at=doc["clicked_at"],
    )


def create_link_click(col: Collection, user, data: LinkClickCreate) -> LinkClickPublic:
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user.id,
        "user_email": user.email,
        "quiz_id": data.quiz_id,
        "question_id": data.question_id,
        "conversation_id": data.conversation_id,
        "url": data.url,
        "clicked_at": now,
    }
    res = col.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _to_public(doc)


def list_link_clicks(col: Collection, user_id: Optional[str] = None) -> List[LinkClickPublic]:
    query: dict = {}
    if user_id is not None:
        query["user_id"] = user_id
    docs = col.find(query).sort("clicked_at", -1)
    return [_to_public(doc) for doc in docs]
