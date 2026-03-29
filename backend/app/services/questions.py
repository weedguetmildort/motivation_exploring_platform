from bson.objectid import ObjectId
from fastapi import HTTPException
from typing import List
from datetime import datetime
from pymongo.collection import Collection
from ..schemas.question import QuestionCreate, QuestionPublic, QuestionAdminPublic, QuestionUpdate

def get_questions_collection(db) -> Collection:
    return db["questions"]

def create_question(col: Collection, data: QuestionCreate) -> QuestionAdminPublic:
    doc = {
        "stem": data.stem,
        "subtitle": data.subtitle,
        "choices": [c.model_dump() for c in data.choices],
        "correct_choice_id": data.correct_choice_id,
        "created_at": datetime.utcnow(),
        "active": True,
    }
    res = col.insert_one(doc)
    doc["_id"] = res.inserted_id
    return QuestionAdminPublic(
        id=str(doc["_id"]),
        stem=doc["stem"],
        subtitle=doc.get("subtitle"),
        choices=doc["choices"],
        correct_choice_id=doc["correct_choice_id"],
    )

def list_questions(col: Collection, limit: int = 100) -> List[QuestionAdminPublic]:
    docs = col.find().sort("created_at", -1).limit(limit)
    items: List[QuestionAdminPublic] = []
    for doc in docs:
        items.append(
            QuestionAdminPublic(
                id=str(doc["_id"]),
                stem=doc["stem"],
                subtitle=doc.get("subtitle"),
                choices=doc["choices"],
                correct_choice_id=doc.get("correct_choice_id", ""),
            )
        )
    return items

def update_question(col, question_id: str, data: QuestionUpdate) -> QuestionPublic:
    try:
        oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question id")

    update_doc = {
        "stem": data.stem,
        "subtitle": data.subtitle,
        "choices": [c.model_dump() for c in data.choices],
    }

    res = col.find_one_and_update(
        {"_id": oid},
        {"$set": update_doc},
        return_document=True,
    )

    if not res:
        raise HTTPException(status_code=404, detail="Question not found")

    return QuestionAdminPublic(
        id=str(res["_id"]),
        stem=res["stem"],
        subtitle=res.get("subtitle"),
        choices=res["choices"],
        correct_choice_id=res.get("correct_choice_id", ""),
    )

def delete_question(col, question_id: str) -> None:
    try:
        oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question id")

    res = col.delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")