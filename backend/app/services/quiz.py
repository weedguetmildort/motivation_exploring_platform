# backend/app/services/quiz.py
import random
import uuid
import hashlib
import json
from datetime import datetime
from typing import Optional
from bson.objectid import ObjectId
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError
from fastapi import HTTPException

from .questions import get_questions_collection
from . import study_flow
from ..core.study_profiles import study_id_of
from ..schemas.quiz import QuizStateResponse, QuizAttemptPublic, QuizQuestionPayload, QuizResultItem, QuizResultsResponse

# ── Quiz 2 (Phase 13 scaffold) ───────────────────────────────────────────────
# Placeholder namespace for a future second quiz version, parallel to quiz 1's
# `base` + followup/links/double. Layout-only for now: completion-flag wiring and
# quiz-2 question pools are deferred. Quiz-2 attempts currently fall through the
# "unknown quiz_id" branch in _get_user_quiz_update_fields (no user-flag update),
# which is intentional until quiz2_*_completed flags are added to the user model.
QUIZ2_BASE_ID = "base2"
QUIZ2_VARIANT_QUIZ_IDS = {"followup2", "double2", "links2"}
QUIZ2_QUIZ_IDS = {QUIZ2_BASE_ID, *QUIZ2_VARIANT_QUIZ_IDS}

MAX_QUIZ_QUESTIONS = 5


def get_users_collection(db) -> Collection:
    return db["users"]


def get_quiz_attempts_collection(db) -> Collection:
    return db["quiz_attempts"]


def _ensure_unique_index(col: Collection) -> None:
    col.create_index(
        [("user_id", 1), ("quiz_id", 1)],
        unique=True,
    )


def _build_pool_query(quiz_set: Optional[str], quiz_sets: Optional[list]) -> dict:
    """The question-pool filter for one attempt, in precedence order.

    1. ``quiz_set`` — the set this specific quiz was assigned
       (study_flow.resolve_quiz_set_assignment). Giving each quiz its own set is
       what makes a participant's four quizzes disjoint: no question can appear
       in two of them, because no question belongs to two sets.
    2. ``quiz_sets`` — the Phase 11 per-participant restriction, which still
       governs any quiz the map does not cover.
    3. Neither — the whole bank, including unassigned (``set: null``) questions.

    Note that two *unmapped* quizzes still draw from the same pool and can
    therefore overlap; mapping every quiz to its own set is what removes that.
    """
    if quiz_set:
        return {"set": quiz_set}
    if quiz_sets:
        # A non-empty list filters to those sets; null-set questions excluded.
        return {"set": {"$in": quiz_sets}}
    return {}


def _load_or_create_attempt(
    db,
    user_id: str,
    user_email: str,
    quiz_id: str,
    quiz_sets: Optional[list] = None,
    quiz_set: Optional[str] = None,
) -> dict:
    col = get_quiz_attempts_collection(db)
    _ensure_unique_index(col)

    doc = col.find_one({"user_id": user_id, "quiz_id": quiz_id})
    if doc:
        return doc

    if quiz_set is None:
        # The participant's stored assignment does not cover this quiz — which
        # is every participant assigned before the map was configured, since it
        # starts empty. Fall back to the current preset map rather than leaving
        # them on the whole pool forever. Only read here, on the rare path where
        # an attempt is actually created.
        quiz_set = study_flow.preset_quiz_set(db, quiz_id)

    qcol = get_questions_collection(db)
    pool_query = _build_pool_query(quiz_set, quiz_sets)

    questions = list(qcol.find(pool_query))
    if not questions:
        raise HTTPException(status_code=400, detail="No questions available for quiz")

    ids = [str(q["_id"]) for q in questions]
    random.shuffle(ids)

    user_doc = db["users"].find_one({"_id": ObjectId(user_id)}) if ObjectId.is_valid(user_id) else None
    user_doc = user_doc or {}
    protocol = user_doc.get("study_protocol") or study_flow.load_study_config(db).as_dict()
    question_count = protocol.get("questions_per_quiz", MAX_QUIZ_QUESTIONS)
    ids = ids[:question_count]
    rate = protocol.get("wrong_ai_rate")
    wrong_count = int(len(ids) * rate + 0.5) if rate is not None else protocol.get("wrong_ai_count", 3)
    incorrect_question_ids = random.sample(ids, min(wrong_count, len(ids)))

    now = datetime.utcnow()
    snapshots = {}
    for question in questions:
        qid = str(question["_id"])
        if qid in ids and question.get("stem") is not None and isinstance(question.get("choices"), list):
            snapshot = {key: question.get(key) for key in ("stem", "subtitle", "choices", "correct_choice_id", "set")}
            snapshot["version"] = hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()
            snapshots[qid] = snapshot
    quiz_order = study_flow.quiz_ids_in_order(user_doc.get("step_order", []))
    doc = {
        "user_id": user_id,
        "user_email": user_email,
        "quiz_id": quiz_id,
        "conversation_id": str(uuid.uuid4()),
        "status": "in_progress",
        "question_order": ids,
        "question_snapshots": snapshots,
        "analytics_schema_version": 1,
        "study_id": study_id_of(db, "study-1"),
        "study_protocol": protocol,
        "requested_question_count": question_count,
        "actual_question_count": len(ids),
        "study_flow_version": user_doc.get("study_flow_version"),
        "variant_sequence": user_doc.get("variant_sequence", []),
        "step_order": user_doc.get("step_order", []),
        "quiz_set_assignment": user_doc.get("quiz_set_assignment", {}),
        "variant_position": quiz_order.index(quiz_id) + 1 if quiz_id in quiz_order else None,
        "is_test": bool(user_doc.get("is_admin", False) or user_doc.get("is_test", False)),
        "incorrect_question_ids": incorrect_question_ids,
        # The set this attempt drew from, recorded at draw time so analysis can
        # see it without re-deriving it from the participant's assignment (which
        # an admin may since have changed). None = drew from the whole pool.
        "question_set": quiz_set,
        "answers": [],
        "created_at": now,
        "updated_at": now,
    }
    try:
        res = col.insert_one(doc)
    except DuplicateKeyError:
        return col.find_one({"user_id": user_id, "quiz_id": quiz_id})
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
    """Mark a quiz attempt as completed and advance the user's study flow."""
    completed_at = datetime.utcnow()
    col = get_quiz_attempts_collection(db)
    col.update_one(
        {"_id": doc["_id"]},
        {"$set": {"status": "completed", "updated_at": completed_at, "completed_at": completed_at}},
    )

    users = get_users_collection(db)
    if not users.count_documents({"_id": ObjectId(doc["user_id"])}, limit=1):
        raise HTTPException(status_code=404, detail="User not found")

    # Progress is now one generic operation: tick this step off the user's
    # assigned step_order, then recompute the derived legacy flags. The old
    # base-vs-variant branching lived here and in three other places;
    # services/study_flow owns all of it now. A quiz_id outside this user's
    # flow (admin test runs, the Phase 13 quiz-2 ids) is simply a no-op.
    study_flow.mark_step_completed(
        db, doc["user_id"], study_flow.quiz_step_id(doc["quiz_id"]), completed_at
    )


def reset_quiz_attempt(db, user_id: str, quiz_id: str) -> None:
    col = get_quiz_attempts_collection(db)
    existing = col.find_one({"user_id": user_id, "quiz_id": quiz_id})
    if existing:
        from .result_archive import archive_result
        archive_result(db, "quiz_attempts", existing, "admin_reset")
    study_flow.unmark_step_completed(db, user_id, study_flow.quiz_step_id(quiz_id))
    # A reset means "redo this quiz from scratch", so pick up any change the
    # admin has made to the question-set map since it was first drawn.
    study_flow.repoint_quiz_set(db, user_id, quiz_id)


def build_quiz_state_response(db, doc: dict) -> QuizStateResponse:
    qcol = get_questions_collection(db)
    question_order = doc.get("question_order", [])
    conv_id = doc.get("conversation_id", "")

    if doc["status"] == "completed":
        # Use raw stored counts — never recompute against current DB state
        total = len(question_order)
        answered = sum(1 for a in doc.get("answers", []) if a.get("answered_at"))
        attempt_pub = QuizAttemptPublic(attempt_id=str(doc.get("_id", "")),
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
    existing_ids = set(doc["question_snapshots"]) if doc.get("question_snapshots") else {
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

    attempt_pub = QuizAttemptPublic(attempt_id=str(doc.get("_id", "")),
        quiz_id=doc["quiz_id"],
        status=doc["status"],
        total_questions=total,
        answered_count=answered,
        incorrect_question_ids=doc.get("incorrect_question_ids", [])
    )

    next_qid = _find_next_unanswered(doc, None if doc.get("question_snapshots") else qcol)
    if not next_qid:
        _mark_quiz_completed(db, doc)
        attempt_pub = QuizAttemptPublic(attempt_id=str(doc.get("_id", "")),
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

    qdoc = doc.get("question_snapshots", {}).get(next_qid) or qcol.find_one({"_id": ObjectId(next_qid)})
    if not qdoc:
        # Race condition: deleted between _find_next_unanswered and here
        _mark_quiz_completed(db, doc)
        attempt_pub = QuizAttemptPublic(attempt_id=str(doc.get("_id", "")),
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
        id=next_qid,
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


def record_answer(db, user_id: str, quiz_id: str, question_id: str, choice_id: str,
                  telemetry_page_id: str | None = None, telemetry_elapsed_ms: float | None = None) -> dict:
    col = get_quiz_attempts_collection(db)

    doc = col.find_one({"user_id": user_id, "quiz_id": quiz_id})
    if not doc:
        raise HTTPException(status_code=400, detail="No quiz attempt found")

    if doc["status"] == "completed":
        original = next((a for a in doc.get("answers", [])
                         if a.get("question_id") == question_id and a.get("answered_at")), None)
        if original and original.get("choice_id") == choice_id:
            study_flow.mark_step_completed(
                db, user_id, study_flow.quiz_step_id(quiz_id),
                doc.get("completed_at") or datetime.utcnow(),
            )
            return doc
        raise HTTPException(status_code=400, detail="Quiz already completed")

    if question_id not in set(doc.get("question_order", [])):
        raise HTTPException(status_code=400, detail="Question not part of this quiz attempt")

    now = datetime.utcnow()

    qcol = get_questions_collection(db)
    qdoc = doc.get("question_snapshots", {}).get(question_id) or qcol.find_one({"_id": ObjectId(question_id)}, {"correct_choice_id": 1})
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
                "answers.$.telemetry_submission": {"page_id": telemetry_page_id, "elapsed_ms": telemetry_elapsed_ms},
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
                        "telemetry_submission": {"page_id": telemetry_page_id, "elapsed_ms": telemetry_elapsed_ms},
                    }
                },
                "$set": {"updated_at": now},
            },
        )

    updated = col.find_one({"_id": doc["_id"]})
    next_qid = _find_next_unanswered(updated, None if updated.get("question_snapshots") else qcol)

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
        qdoc = doc.get("question_snapshots", {}).get(qid) or qcol.find_one({"_id": ObjectId(qid)}, {"stem": 1, "choices": 1, "correct_choice_id": 1})
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
