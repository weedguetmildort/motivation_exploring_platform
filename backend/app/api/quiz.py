# backend/app/api/quiz.py
from fastapi import APIRouter, Depends, Request, HTTPException
from ..schemas.user import UserPublic
from .auth import get_current_user
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


def require_quiz_access(
    request: Request, user: UserPublic = Depends(get_current_user)
) -> UserPublic:
    """Allow a main-study quiz only when it is the participant's current step.

    Enforced server-side, not just by the page's redirects, so a participant
    cannot skip ahead in the flow (or redo a finished quiz) by typing a URL.

    Two deliberate exemptions:
      * admins, so the playground can still exercise any variant out of order;
      * any quiz_id the main-study registry doesn't know — notably the Phase 13
        quiz-2 ids (base2/followup2/...), which are gated by
        followup_study_granted rather than by this flow. Those keep exactly the
        access behaviour they have today.
    """
    quiz_id = request.path_params["quiz_id"]

    if user.is_admin or not study_flow.is_known_quiz_id(quiz_id):
        return user

    step_id = study_flow.quiz_step_id(quiz_id)

    if step_id not in user.step_order:
        raise HTTPException(status_code=403, detail="Quiz is not part of your study flow")

    if not study_flow.is_step_unlocked_for(user.step_order, user.completed_steps, step_id):
        raise HTTPException(status_code=403, detail="This quiz is not your current step")

    return user


@router.get("/state", response_model=QuizStateResponse)
def get_quiz_state(request: Request, user: UserPublic = Depends(require_quiz_access)):
    db = request.app.state.db
    quiz_id = request.path_params["quiz_id"]
    attempt_doc = _load_or_create_attempt(
        db, user.id, user.email, quiz_id, quiz_sets=user.quiz_sets
    )

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
