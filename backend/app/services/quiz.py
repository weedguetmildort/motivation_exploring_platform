# backend/app/services/quiz.py
import uuid
from datetime import datetime
from typing import Optional
from bson.objectid import ObjectId
from pymongo.collection import Collection
from fastapi import HTTPException

from .questions import get_questions_collection
from ..schemas.quiz import QuizStateResponse, QuizAttemptPublic, QuizQuestionPayload, QuizResultItem, QuizResultsResponse
from ..schemas.user import SurveyStage, AssignedVar

_VARIANT_QUIZ_IDS = {v.value for v in AssignedVar}

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

    incorrect_count = random.randint(3, min(5,len(ids)))
    incorrect_question_ids = random.sample(ids, incorrect_count)

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


def _find_next_unanswered(doc: dict, qcol=None) -> Optional[str]:
    answered_map = {a["question_id"] for a in doc.get("answers", []) if a.get("answered_at")}
    for qid in doc.get("question_order", []):
        if qid in answered_map:
            continue
        if qcol is not None and not qcol.count_documents({"_id": ObjectId(qid)}, limit=1):
            continue  # question was deleted, skip it
        return qid
    return None


def _mark_quiz_completed(db, doc: dict) -> None:
    """Mark a quiz attempt as completed and update user-level completion flags."""
    completed_at = datetime.utcnow()
    col = get_quiz_attempts_collection(db)
    col.update_one(
        {"_id": doc["_id"]},
        {"$set": {"status": "completed", "updated_at": completed_at}},
    )
    users = get_users_collection(db)
    user_set_doc = _get_user_quiz_update_fields(doc["quiz_id"], completed_at)
    result = users.update_one(
        {"_id": ObjectId(doc["user_id"])},
        {"$set": user_set_doc},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")


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

    if quiz_id in _VARIANT_QUIZ_IDS:
        return {
            "quiz_variant_completed": True,
            "survey_stage": SurveyStage.post_variant.value,
            "updated_at": completed_at,
        }
        
    # Unknown quiz_id (e.g. admin test runs) — don't update user flags
    return {"updated_at": completed_at}


def reset_quiz_attempt(db, user_id: str, quiz_id: str) -> None:
    col = get_quiz_attempts_collection(db)
    col.delete_one({"user_id": user_id, "quiz_id": quiz_id})

    if quiz_id == "base":
        revert = {
            "quiz_base_completed": False,
            "survey_stage": SurveyStage.pre_base.value,
            "updated_at": datetime.utcnow(),
        }
    elif quiz_id in _VARIANT_QUIZ_IDS:
        revert = {
            "quiz_variant_completed": False,
            "survey_stage": SurveyStage.post_base.value,
            "updated_at": datetime.utcnow(),
        }
    else:
        # Unknown quiz_id (e.g. admin test runs) — just delete the attempt, no user flags to revert
        return

    users = get_users_collection(db)
    users.update_one({"_id": ObjectId(user_id)}, {"$set": revert})


def build_quiz_state_response(db, doc: dict) -> QuizStateResponse:
    qcol = get_questions_collection(db)
    question_order = doc.get("question_order", [])
    conv_id = doc.get("conversation_id", "")

    if doc["status"] == "completed":
        # Use raw stored counts — never recompute against current DB state
        total = len(question_order)
        answered = sum(1 for a in doc.get("answers", []) if a.get("answered_at"))
        attempt_pub = QuizAttemptPublic(
            quiz_id=doc["quiz_id"],
            status=doc["status"],
            total_questions=total,
            answered_count=answered,
            incorrect_question_ids=doc.get("incorrect_question_ids", [])
        )
        return QuizStateResponse(
            conversation_id=conv_id,
            attempt=attempt_pub,
            current_question=None,
        )

    # In-progress: filter total/answered to only questions that still exist in the DB
    existing_ids = {
        str(q["_id"])
        for q in qcol.find(
            {"_id": {"$in": [ObjectId(qid) for qid in question_order]}},
            {"_id": 1},
        )
    }
    total = len(existing_ids)
    answered = sum(
        1 for a in doc.get("answers", [])
        if a.get("answered_at") and a["question_id"] in existing_ids
    )

    attempt_pub = QuizAttemptPublic(
        quiz_id=doc["quiz_id"],
        status=doc["status"],
        total_questions=total,
        answered_count=answered,
        incorrect_question_ids=doc.get("incorrect_question_ids", [])
    )

    next_qid = _find_next_unanswered(doc, qcol)
    if not next_qid:
        _mark_quiz_completed(db, doc)
        attempt_pub = QuizAttemptPublic(
            quiz_id=doc["quiz_id"],
            status="completed",
            total_questions=total,
            answered_count=answered,
            incorrect_question_ids=doc.get("incorrect_question_ids", [])
        )
        return QuizStateResponse(
            conversation_id=conv_id,
            attempt=attempt_pub,
            current_question=None,
        )

    qdoc = qcol.find_one({"_id": ObjectId(next_qid)})
    if not qdoc:
        # Race condition: deleted between _find_next_unanswered and here
        _mark_quiz_completed(db, doc)
        attempt_pub = QuizAttemptPublic(
            quiz_id=doc["quiz_id"],
            status="completed",
            total_questions=total,
            answered_count=answered,
            incorrect_question_ids=doc.get("incorrect_question_ids", [])
        )
        return QuizStateResponse(
            conversation_id=conv_id,
            attempt=attempt_pub,
            current_question=None,
        )

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

    qcol = get_questions_collection(db)
    qdoc = qcol.find_one({"_id": ObjectId(question_id)}, {"correct_choice_id": 1})
    is_correct = bool(qdoc and qdoc.get("correct_choice_id") == choice_id)

    res = col.update_one(
        {
            "_id": doc["_id"],
            "answers.question_id": question_id,
        },
        {
            "$set": {
                "answers.$.choice_id": choice_id,
                "answers.$.answered_at": now,
                "answers.$.marked_correct": is_correct,
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
                        "marked_correct": is_correct,
                    }
                },
                "$set": {"updated_at": now},
            },
        )

    updated = col.find_one({"_id": doc["_id"]})
    next_qid = _find_next_unanswered(updated, qcol)

    if not next_qid:
        _mark_quiz_completed(db, updated)
        updated = col.find_one({"_id": updated["_id"]})

    return updated

# (Admin view for now) Get incorrect questions (id, selected and correct answers) and completion score
def get_quiz_results(db, user_id: str, quiz_id: str) -> QuizResultsResponse:
    col = get_quiz_attempts_collection(db)
    doc = col.find_one({"user_id": user_id, "quiz_id": quiz_id})
    if not doc:
        raise HTTPException(status_code=404, detail="No quiz attempt found")

    qcol = get_questions_collection(db)
    question_order = doc.get("question_order", [])
    answers_by_qid = {a["question_id"]: a for a in doc.get("answers", []) if a.get("answered_at")}

    items = []
    for qid in question_order:
        ans = answers_by_qid.get(qid)
        if not ans:
            continue
        qdoc = qcol.find_one({"_id": ObjectId(qid)}, {"stem": 1, "choices": 1, "correct_choice_id": 1})
        if not qdoc:
            continue

        choices_map = {c["id"]: c["label"] for c in qdoc.get("choices", [])}
        correct_id = qdoc.get("correct_choice_id", "")
        user_id_choice = ans.get("choice_id", "")

        items.append(QuizResultItem(
            question_number=question_order.index(qid) + 1,
            question_id=qid,
            stem=qdoc["stem"],
            user_choice_id=user_id_choice,
            user_choice_label=choices_map.get(user_id_choice, ""),
            correct_choice_id=correct_id,
            correct_choice_label=choices_map.get(correct_id, ""),
            is_correct=bool(ans.get("marked_correct")),
        ))

    correct_count = sum(1 for item in items if item.is_correct)
    return QuizResultsResponse(
        quiz_id=quiz_id,
        total_questions=len(items),
        correct_count=correct_count,
        items=items,
    )