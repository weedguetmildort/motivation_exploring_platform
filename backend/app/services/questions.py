from bson.objectid import ObjectId
from fastapi import HTTPException
from typing import List
from datetime import datetime
from pymongo.collection import Collection
from ..schemas.question import QuestionCreate, QuestionPublic, QuestionUpdate

def get_questions_collection(db) -> Collection:
    return db["questions"]

def create_question(col: Collection, data: QuestionCreate) -> QuestionPublic:
    doc = {
        "stem": data.stem,
        "subtitle": data.subtitle,
        "choices": [c.model_dump() for c in data.choices],
        "created_at": datetime.utcnow(),
        "active": True,
    }
    res = col.insert_one(doc)
    doc["_id"] = res.inserted_id
    return QuestionPublic(
        id=str(doc["_id"]),
        stem=doc["stem"],
        subtitle=doc.get("subtitle"),
        choices=doc["choices"],
    )

def list_questions(col: Collection, limit: int = 100) -> List[QuestionPublic]:
    docs = col.find().sort("created_at", -1).limit(limit)
    items: List[QuestionPublic] = []
    for doc in docs:
        items.append(
            QuestionPublic(
                id=str(doc["_id"]),
                stem=doc["stem"],
                subtitle=doc.get("subtitle"),
                choices=doc["choices"],
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

    return QuestionPublic(
        id=str(res["_id"]),
        stem=res["stem"],
        subtitle=res.get("subtitle"),
        choices=res["choices"],
    )

def delete_question(col, question_id: str) -> None:
    try:
        oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question id")

    res = col.delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")