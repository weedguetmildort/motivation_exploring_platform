# backend/app/services/copy_events.py
from typing import Optional, List
from datetime import datetime, timezone
from pymongo.collection import Collection

from ..schemas.copy_event import CopyEventCreate, CopyEventPublic


def get_copy_events_collection(db) -> Collection:
    return db["copy_events"]


def ensure_indexes(col: Collection) -> None:
    col.create_index("user_id")
    col.create_index("conversation_id")
    col.create_index([("created_at", -1)])


def _to_public(doc: dict) -> CopyEventPublic:
    return CopyEventPublic(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        user_email=doc["user_email"],
        quiz_id=doc.get("quiz_id"),
        question_id=doc.get("question_id"),
        conversation_id=doc.get("conversation_id"),
        copied_text=doc["copied_text"],
        created_at=doc["created_at"],
    )


def create_copy_event(col: Collection, user, data: CopyEventCreate) -> CopyEventPublic:
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user.id,
        "user_email": user.email,
        "quiz_id": data.quiz_id,
        "question_id": data.question_id,
        "conversation_id": data.conversation_id,
        "copied_text": data.copied_text,
        "created_at": now,
    }
    res = col.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _to_public(doc)


def list_copy_events(col: Collection, user_id: Optional[str] = None) -> List[CopyEventPublic]:
    query: dict = {}
    if user_id is not None:
        query["user_id"] = user_id
    docs = col.find(query).sort("created_at", -1)
    return [_to_public(doc) for doc in docs]
