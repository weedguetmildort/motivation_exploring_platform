from bson.objectid import ObjectId
from fastapi import HTTPException
from typing import List, Optional
from datetime import datetime
from pymongo.collection import Collection
from ..schemas.question import (
    QuestionCreate,
    QuestionPublic,
    QuestionAdminPublic,
    QuestionUpdate,
    SetId,
    Difficulty,
)

def get_questions_collection(db) -> Collection:
    return db["questions"]


def _to_admin_public(doc: dict) -> QuestionAdminPublic:
    """Map a raw Mongo doc to the admin view, backfilling Phase 8 fields for
    legacy documents that predate set/difficulty."""
    return QuestionAdminPublic(
        id=str(doc["_id"]),
        stem=doc["stem"],
        subtitle=doc.get("subtitle"),
        choices=doc["choices"],
        correct_choice_id=doc.get("correct_choice_id", ""),
        set=doc.get("set"),
        difficulty=doc.get("difficulty"),
        difficulty_source=doc.get("difficulty_source"),
        difficulty_checked=doc.get("difficulty_checked", False),
    )


def create_question(col: Collection, data: QuestionCreate) -> QuestionAdminPublic:
    doc = {
        "stem": data.stem,
        "subtitle": data.subtitle,
        "choices": [c.model_dump() for c in data.choices],
        "correct_choice_id": data.correct_choice_id,
        "set": data.set,
        "difficulty": None,
        "difficulty_source": None,
        "difficulty_checked": False,
        "created_at": datetime.utcnow(),
        "active": True,
    }
    res = col.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _to_admin_public(doc)

def list_questions(col: Collection, limit: int = 100) -> List[QuestionAdminPublic]:
    docs = col.find().sort("created_at", -1).limit(limit)
    return [_to_admin_public(doc) for doc in docs]

def update_question(col, question_id: str, data: QuestionUpdate) -> QuestionAdminPublic:
    try:
        oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question id")

    existing = col.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Question not found")

    # `set` is intentionally NOT written here — it is managed via assign_set so a
    # plain content edit never wipes the assignment.
    update_doc = {
        "stem": data.stem,
        "subtitle": data.subtitle,
        "choices": [c.model_dump() for c in data.choices],
        "correct_choice_id": data.correct_choice_id,
    }

    # Re-judge on edit: reset an AI-assigned difficulty so the next AI pass
    # re-evaluates the changed content. A manual override is preserved.
    if existing.get("difficulty_source") != "manual":
        update_doc["difficulty"] = None
        update_doc["difficulty_source"] = None
        update_doc["difficulty_checked"] = False

    res = col.find_one_and_update(
        {"_id": oid},
        {"$set": update_doc},
        return_document=True,
    )

    if not res:
        raise HTTPException(status_code=404, detail="Question not found")

    return _to_admin_public(res)

def assign_set(col, question_id: str, set_value: Optional[SetId]) -> QuestionAdminPublic:
    try:
        oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question id")

    res = col.find_one_and_update(
        {"_id": oid},
        {"$set": {"set": set_value}},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Question not found")
    return _to_admin_public(res)

def override_difficulty(col, question_id: str, difficulty: Optional[Difficulty]) -> QuestionAdminPublic:
    try:
        oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question id")

    if difficulty is None:
        # Clearing a manual difficulty returns the question to the unjudged pool.
        update_doc = {"difficulty": None, "difficulty_source": None, "difficulty_checked": False}
    else:
        update_doc = {"difficulty": difficulty, "difficulty_source": "manual", "difficulty_checked": True}

    res = col.find_one_and_update(
        {"_id": oid},
        {"$set": update_doc},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Question not found")
    return _to_admin_public(res)

def delete_question(col, question_id: str) -> None:
    try:
        oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question id")

    res = col.delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")
