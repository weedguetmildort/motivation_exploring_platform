# backend/app/services/quiz.py
import uuid
from datetime import datetime
from typing import Optional
from bson.objectid import ObjectId
from pymongo.collection import Collection
from fastapi import HTTPException

from .questions import get_questions_collection
from ..schemas.quiz import QuizStateResponse, QuizAttemptPublic, QuizQuestionPayload
from ..schemas.user import SurveyStage

MAX_QUIZ_QUESTIONS = 10


def get_users_collection(db) -> Collection:
    return db["users"]


def get_quiz_attempts_collection(db) -> Collection:
    return db["quiz_attempts"]


def _ensure_unique_index(col: Collection) -> None:
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
        "conversation_id": str(uuid.uuid4()),
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


def _get_user_quiz_update_fields(quiz_id: str, completed_at: datetime) -> dict:
    """
    Decide which user-level completion flag and next survey_stage should be set
    when a quiz is completed.

    Adjust the quiz_id values here to match your actual routing / DB values.
    """
    if quiz_id == "base":
        return {
            "quiz_base_completed": True,
            "survey_stage": SurveyStage.post_base.value,
            "updated_at": completed_at,
        }

    if quiz_id == "variant":
        return {
            "quiz_variant_completed": True,
            "survey_stage": SurveyStage.post_variant.value,
            "updated_at": completed_at,
        }

    raise HTTPException(status_code=400, detail=f"Unknown quiz_id for completion flow: {quiz_id}")


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

    conv_id = doc.get("conversation_id", "")

    if doc["status"] == "completed":
        return QuizStateResponse(
            conversation_id=conv_id,
            attempt=attempt_pub,
            current_question=None,
        )

    next_qid = _find_next_unanswered(doc)
    if not next_qid:
        return QuizStateResponse(
            conversation_id=conv_id,
            attempt=attempt_pub,
            current_question=None,
        )

    qdoc = qcol.find_one({"_id": ObjectId(next_qid)})
    if not qdoc:
        raise HTTPException(status_code=500, detail="Question not found")

    question_payload = QuizQuestionPayload(
        id=str(qdoc["_id"]),
        stem=qdoc["stem"],
        subtitle=qdoc.get("subtitle"),
        choices=qdoc["choices"],
    )

    return QuizStateResponse(
        conversation_id=conv_id,
        attempt=attempt_pub,
        current_question=question_payload,
    )


def record_question_shown(db, doc: dict, question_id: str) -> dict:
    col = get_quiz_attempts_collection(db)

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

    updated = col.find_one({"_id": doc["_id"]})
    next_qid = _find_next_unanswered(updated)

    if not next_qid:
        completed_at = datetime.utcnow()

        col.update_one(
            {"_id": updated["_id"]},
            {
                "$set": {
                    "status": "completed",
                    "updated_at": completed_at,
                }
            },
        )

        users = get_users_collection(db)
        user_set_doc = _get_user_quiz_update_fields(quiz_id, completed_at)

        result = users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": user_set_doc},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")

        updated = col.find_one({"_id": updated["_id"]})

    return updated