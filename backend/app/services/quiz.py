# backend/app/services/quiz.py
from datetime import datetime
from typing import Optional, List, Tuple
from bson.objectid import ObjectId
from pymongo.collection import Collection
from fastapi import HTTPException

from .questions import get_questions_collection  # assuming you have this
from ..schemas.quiz import QuizStateResponse, QuizAttemptPublic, QuizQuestionPayload

#QUIZ_ID = "main"  # single quiz for now
MAX_QUIZ_QUESTIONS = 10

def get_quiz_attempts_collection(db) -> Collection:
    return db["quiz_attempts"]

def _ensure_unique_index(col: Collection) -> None:
    # one attempt doc per (user_id, quiz_id)
    col.create_index(
        [("user_id", 1), ("quiz_id", 1)],
        unique=True,
    )

def _load_or_create_attempt(db, user_id: str, user_email: str, quiz_id: str) -> dict:
    col = get_quiz_attempts_collection(db)
    _ensure_unique_index(col)

    doc = col.find_one({"user_id": user_id, "quiz_id": quiz_id})
    if doc:
        return doc

    # create new attempt with randomized question order
    qcol = get_questions_collection(db)
    questions = list(qcol.find({}, {"_id": 1}))
    if not questions:
        raise HTTPException(status_code=400, detail="No questions available for quiz")

    ids = [str(q["_id"]) for q in questions]

    import random
    random.shuffle(ids)

    ids = ids[:MAX_QUIZ_QUESTIONS]

    now = datetime.utcnow()
    doc = {
        "user_id": user_id,
        "user_email": user_email,
        "quiz_id": quiz_id,
        "status": "in_progress",
        "question_order": ids,
        "answers": [],
        "created_at": now,
        "updated_at": now,
    }
    res = col.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc

def _find_next_unanswered(doc: dict) -> Optional[str]:
    answered_map = {a["question_id"] for a in doc.get("answers", []) if a.get("answered_at")}
    for qid in doc.get("question_order", []):
        if qid not in answered_map:
            return qid
    return None

def build_quiz_state_response(db, doc: dict) -> QuizStateResponse:
    qcol = get_questions_collection(db)
    total = len(doc.get("question_order", []))
    answered = sum(1 for a in doc.get("answers", []) if a.get("answered_at"))

    attempt_pub = QuizAttemptPublic(
        quiz_id=doc["quiz_id"],
        status=doc["status"],
        total_questions=total,
        answered_count=answered,
    )

    if doc["status"] == "completed":
        # don't send a current question
        return QuizStateResponse(attempt=attempt_pub, current_question=None)

    next_qid = _find_next_unanswered(doc)
    if not next_qid:
        # nothing left but status not marked complete -> fix it
        return QuizStateResponse(attempt=attempt_pub, current_question=None)

    qdoc = qcol.find_one({"_id": ObjectId(next_qid)})
    if not qdoc:
        raise HTTPException(status_code=500, detail="Question not found")

    question_payload = QuizQuestionPayload(
        id=str(qdoc["_id"]),
        stem=qdoc["stem"],
        subtitle=qdoc.get("subtitle"),
        choices=qdoc["choices"],
    )

    return QuizStateResponse(attempt=attempt_pub, current_question=question_payload)

def record_question_shown(db, doc: dict, question_id: str) -> dict:
    col = get_quiz_attempts_collection(db)

    # if there's already an answer record for this question, don't duplicate it
    has = any(a["question_id"] == question_id for a in doc.get("answers", []))
    now = datetime.utcnow()

    if not has:
        col.update_one(
            {"_id": doc["_id"]},
            {
                "$push": {
                    "answers": {
                        "question_id": question_id,
                        "shown_at": now,
                        "answered_at": None,
                        "choice_id": None,
                    }
                },
                "$set": {"updated_at": now},
            },
        )
        doc = col.find_one({"_id": doc["_id"]})
    return doc

def record_answer(db, user_id: str, quiz_id: str, question_id: str, choice_id: str) -> dict:
    col = get_quiz_attempts_collection(db)

    doc = col.find_one({"user_id": user_id, "quiz_id": quiz_id})
    if not doc:
        raise HTTPException(status_code=400, detail="No quiz attempt found")

    if doc["status"] == "completed":
        raise HTTPException(status_code=400, detail="Quiz already completed")
    
    if question_id not in set(doc.get("question_order", [])):
        raise HTTPException(status_code=400, detail="Question not part of this quiz attempt")

    now = datetime.utcnow()

    # update the answer entry (or create it if somehow missing)
    res = col.update_one(
        {
            "_id": doc["_id"],
            "answers.question_id": question_id,
        },
        {
            "$set": {
                "answers.$.choice_id": choice_id,
                "answers.$.answered_at": now,
                "updated_at": now,
            }
        },
    )

    if res.matched_count == 0:
        # There was no existing answer record; create one now
        col.update_one(
            {"_id": doc["_id"]},
            {
                "$push": {
                    "answers": {
                        "question_id": question_id,
                        "shown_at": now,
                        "answered_at": now,
                        "choice_id": choice_id,
                    }
                },
                "$set": {"updated_at": now},
            },
        )

    # check if we finished
    updated = col.find_one({"_id": doc["_id"]})
    next_qid = _find_next_unanswered(updated)
    if not next_qid:
        col.update_one(
            {"_id": updated["_id"]},
            {"$set": {"status": "completed", "updated_at": datetime.utcnow()}},
        )
        updated = col.find_one({"_id": updated["_id"]})

    return updated
