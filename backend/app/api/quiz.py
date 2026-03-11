# backend/app/api/quiz.py
from fastapi import APIRouter, Depends, Request, HTTPException
from ..schemas.user import UserPublic
from .auth import get_current_user
from ..schemas.quiz import QuizStateResponse, SubmitAnswerRequest
from ..services.quiz import (
    _load_or_create_attempt,
    build_quiz_state_response,
    record_question_shown,
    record_answer,
)

#TODO: ensure quiz_id is valid - either in this file before querying responses or in services/quiz.py functions
# Doing in this file is a bit more organized but doing it from services avoids doing an additional mongoDB request
router = APIRouter(prefix="/quiz/{quiz_id}", tags=["quiz"])

@router.get("/state", response_model=QuizStateResponse)
def get_quiz_state(request: Request, user: UserPublic = Depends(get_current_user)):
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
    user: UserPublic = Depends(get_current_user),
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
