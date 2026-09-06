# backend/app/api/quiz.py
from fastapi import APIRouter, Depends, Request, HTTPException
from ..schemas.user import UserPublic
from .auth import build_user_public, get_current_user, get_current_user_doc
from ..schemas.quiz import QuizStateResponse, SubmitAnswerRequest, QuizResultsResponse
from ..services import study_flow
from ..services.quiz import (
    _load_or_create_attempt,
    build_quiz_state_response,
    record_question_shown,
    record_answer,
    reset_quiz_attempt,
    get_quiz_results,
)

router = APIRouter(prefix="/quiz/{quiz_id}", tags=["quiz"])


def require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def require_quiz_access(request: Request) -> UserPublic:
    """Allow a quiz only when it is the participant's current step.

    Enforced server-side, not just in the page, so a participant cannot skip
    ahead in the flow (or redo a finished quiz) by typing a URL. Admins are
    exempt so they can still exercise any variant from the playground.
    """
    doc = get_current_user_doc(request)
    quiz_id = request.path_params["quiz_id"]

    if doc.get("is_admin"):
        return build_user_public(doc)

    if not study_flow.is_known_quiz_id(quiz_id):
        raise HTTPException(status_code=404, detail="Unknown quiz")

    step_id = study_flow.quiz_step_id(quiz_id)

    if step_id not in (doc.get("step_order") or []):
        raise HTTPException(status_code=403, detail="Quiz is not part of your study flow")

    if not study_flow.is_step_unlocked(doc, step_id):
        raise HTTPException(status_code=403, detail="This quiz is not your current step")

    return build_user_public(doc)


@router.get("/state", response_model=QuizStateResponse)
def get_quiz_state(request: Request, user: UserPublic = Depends(require_quiz_access)):
    db = request.app.state.db
    quiz_id = request.path_params["quiz_id"]
    attempt_doc = _load_or_create_attempt(db, user.id, user.email, quiz_id)

    # If quiz is completed, just return state
    if attempt_doc["status"] == "completed":
        return build_quiz_state_response(db, attempt_doc)

    # Otherwise, ensure we record "shown_at" for the current question
    state = build_quiz_state_response(db, attempt_doc)
    if state.current_question is not None:
        attempt_doc = record_question_shown(
            db, attempt_doc, state.current_question.id
        )
        # rebuild state from updated doc
        state = build_quiz_state_response(db, attempt_doc)

    return state

@router.post("/answer", response_model=QuizStateResponse)
def submit_quiz_answer(
    data: SubmitAnswerRequest,
    request: Request,
    user: UserPublic = Depends(require_quiz_access),
):
    db = request.app.state.db
    quiz_id = request.path_params["quiz_id"]

    updated_doc = record_answer(
        db,
        user_id=user.id,
        quiz_id=quiz_id,
        question_id=data.question_id,
        choice_id=data.choice_id,
    )

    return build_quiz_state_response(db, updated_doc)

# Admin endpoint to get quiz results for a given quiz attempt
@router.get("/results", response_model=QuizResultsResponse)
def get_quiz_results_endpoint(
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    db = request.app.state.db
    quiz_id = request.path_params["quiz_id"]
    return get_quiz_results(db, user.id, quiz_id)


@router.post("/reset", status_code=200)
def reset_quiz(
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    db = request.app.state.db
    quiz_id = request.path_params["quiz_id"]
    reset_quiz_attempt(db, user.id, quiz_id)
    return {"ok": True}
