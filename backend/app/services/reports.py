# backend/app/services/reports.py
from typing import Optional, List
from datetime import datetime, timezone
import uuid
from pymongo.collection import Collection
from bson import ObjectId

from ..schemas.report import (
    ReportCategory,
    ReportStatus,
    ReportCreate,
    ReportPublic,
    CommentPublic,
)


def get_reports_collection(db) -> Collection:
    return db["reports"]


def ensure_indexes(col: Collection) -> None:
    col.create_index("user_id")
    col.create_index("status")
    col.create_index([("created_at", -1)])


def _to_public(doc: dict) -> ReportPublic:
    raw_category = doc.get("category", "other")
    try:
        category = ReportCategory(raw_category)
    except ValueError:
        category = ReportCategory.OTHER

    raw_status = doc.get("status", "open")
    try:
        status = ReportStatus(raw_status)
    except ValueError:
        status = ReportStatus.OPEN

    comments = [
        CommentPublic(
            id=c["id"],
            author_email=c["author_email"],
            is_admin=c.get("is_admin", False),
            body=c["body"],
            created_at=c["created_at"],
        )
        for c in doc.get("comments", [])
    ]

    return ReportPublic(
        id=str(doc["_id"]),
        user_email=doc["user_email"],
        quiz_id=doc.get("quiz_id"),
        question_id=doc.get("question_id"),
        category=category,
        description=doc["description"],
        status=status,
        comments=comments,
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


def create_report(col: Collection, user, data: ReportCreate) -> ReportPublic:
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user.id,
        "user_email": user.email,
        "quiz_id": data.quiz_id,
        "question_id": data.question_id,
        "category": data.category.value,
        "description": data.description.strip(),
        "status": ReportStatus.OPEN.value,
        "comments": [],
        "created_at": now,
        "updated_at": now,
    }
    res = col.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _to_public(doc)


def list_reports(
    col: Collection,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[ReportPublic]:
    query: dict = {}
    if user_id is not None:
        query["user_id"] = user_id
    if status is not None:
        query["status"] = status
    docs = col.find(query).sort("created_at", -1)
    return [_to_public(doc) for doc in docs]


def get_report(
    col: Collection,
    report_id: str,
    user_id: Optional[str] = None,
) -> Optional[ReportPublic]:
    if not ObjectId.is_valid(report_id):
        return None
    query: dict = {"_id": ObjectId(report_id)}
    if user_id is not None:
        query["user_id"] = user_id
    doc = col.find_one(query)
    return _to_public(doc) if doc else None


def add_comment(
    col: Collection,
    report_id: str,
    user,
    body: str,
    user_id: Optional[str] = None,
) -> Optional[ReportPublic]:
    if not ObjectId.is_valid(report_id):
        return None
    query: dict = {"_id": ObjectId(report_id)}
    if user_id is not None:
        query["user_id"] = user_id
    now = datetime.now(timezone.utc)
    comment = {
        "id": str(uuid.uuid4()),
        "author_email": user.email,
        "is_admin": user.is_admin,
        "body": body.strip(),
        "created_at": now,
    }
    result = col.update_one(
        query,
        {"$push": {"comments": comment}, "$set": {"updated_at": now}},
    )
    if result.matched_count == 0:
        return None
    doc = col.find_one({"_id": ObjectId(report_id)})
    return _to_public(doc) if doc else None


def update_status(
    col: Collection,
    report_id: str,
    status: ReportStatus,
) -> Optional[ReportPublic]:
    if not ObjectId.is_valid(report_id):
        return None
    now = datetime.now(timezone.utc)
    result = col.update_one(
        {"_id": ObjectId(report_id)},
        {"$set": {"status": status.value, "updated_at": now}},
    )
    if result.matched_count == 0:
        return None
    doc = col.find_one({"_id": ObjectId(report_id)})
    return _to_public(doc) if doc else None
