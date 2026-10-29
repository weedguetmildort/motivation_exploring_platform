'''
Services for the quiz that are specifically for analysis after completion rather than for the quiz flow itself. These are not currently used by any API endpoints but can be imported and used in ad-hoc scripts or new endpoints as needed.

get_question_accuracy(): query accuracy across all users for a specific question.
- Optional filter by quiz id
get_quiz_accuracy(): query overall accuracy for a quiz type across all users.
get_user_quiz_accuracy(): query accuracy for a specific user on a specific quiz.

Useful for determining how the quiz type impacts accuracy overall and for different types of questions.
Accuracy denominators (total / total_answers) include only submitted answers
with a stored grade or an immutable answer key. Missing grades are counted separately.
'''

from .quiz import get_quiz_attempts_collection
from ..schemas.user import AssignedVar
from .quiz_grading import answer_correctness

_VARIANT_QUIZ_IDS = [v.value for v in AssignedVar]

def get_question_accuracy(db, question_id: str, quiz_id: str | None = None) -> dict:
    """
    Returns accuracy for a specific question across all users.
    If quiz_id is passed, filters to only that quiz type.
    """
    col = get_quiz_attempts_collection(db)
    query = {"answers.question_id": question_id}
    if quiz_id:
        query["quiz_id"] = quiz_id

    attempts = col.find(query, {"answers": 1, "quiz_id": 1, "question_snapshots": 1})
    total, correct, ungraded = 0, 0, 0
    for attempt in attempts:
        for ans in attempt.get("answers", []):
            if ans.get("question_id") == question_id and ans.get("answered_at"):
                grade = answer_correctness(ans, attempt.get("question_snapshots", {}).get(question_id))
                if grade is None:
                    ungraded += 1
                    continue
                total += 1
                if grade:
                    correct += 1

    accuracy = correct / total if total > 0 else None
    return {
        "question_id": question_id,
        "quiz_id": quiz_id,
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "answers_missing_grade": ungraded,
    }


def get_user_quiz_accuracy(db, user_id: str, quiz_type: str) -> dict:
    """
    Returns accuracy for a specific user on a quiz type.
    quiz_type must be "base" or "variant".

    NOTE: with quiz_type="variant" this returns an arbitrary one of the user's
    variant attempts when a participant has completed several of them.
    """
    if quiz_type == "base":
        quiz_filter = "base"
    else:
        quiz_filter = {"$in": _VARIANT_QUIZ_IDS}

    col = get_quiz_attempts_collection(db)
    query = {"user_id": user_id, "quiz_id": quiz_filter, "status": "completed"}
    projection = {"answers": 1, "quiz_id": 1, "question_snapshots": 1}
    if quiz_type == "base":
        attempt = col.find_one(query, projection)
        attempts = [attempt] if attempt else []
    else:
        attempts = list(col.find(query, projection))
    if not attempts:
        return {
            "user_id": user_id,
            "quiz_type": quiz_type,
            "quiz_id": None,
            "total": 0,
            "correct": 0,
            "accuracy": None,
              "answers_missing_grade": 0,
        }

    total, correct, ungraded = 0, 0, 0
    for attempt in attempts:
        for ans in attempt.get("answers", []):
            if ans.get("answered_at"):
                grade = answer_correctness(ans, attempt.get("question_snapshots", {}).get(ans.get("question_id")))
                if grade is None:
                    ungraded += 1
                    continue
                total += 1
                if grade:
                    correct += 1

    accuracy = correct / total if total > 0 else None
    return {
        "user_id": user_id,
        "quiz_type": quiz_type,
        "quiz_id": attempts[0]["quiz_id"] if len(attempts) == 1 else None,
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "answers_missing_grade": ungraded,
    }


def get_quiz_accuracy(db, quiz_id: str) -> dict:
    """
    Returns overall accuracy (% correct) for a specific quiz type across all users.
    """
    col = get_quiz_attempts_collection(db)
    attempts = list(col.find({"quiz_id": quiz_id, "status": "completed"}, {"answers": 1, "question_snapshots": 1}))
    total, correct, ungraded = 0, 0, 0
    for attempt in attempts:
        for ans in attempt.get("answers", []):
            if ans.get("answered_at"):
                grade = answer_correctness(ans, attempt.get("question_snapshots", {}).get(ans.get("question_id")))
                if grade is None:
                    ungraded += 1
                    continue
                total += 1
                if grade:
                    correct += 1

    accuracy = correct / total if total > 0 else None
    return {
        "quiz_id": quiz_id,
        "attempts": len(attempts),
        "total_answers": total,
        "correct": correct,
        "accuracy": accuracy,
        "answers_missing_grade": ungraded,
    }
