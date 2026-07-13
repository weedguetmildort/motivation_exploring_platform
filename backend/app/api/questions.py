from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from ..schemas.question import (
    QuestionCreate,
    QuestionAdminPublic,
    QuestionUpdate,
    SetAssign,
    DifficultyOverride,
)
from ..schemas.user import UserPublic
from .auth import get_current_user
from ..core.llm import get_sync_llm_client
from ..services.questions import (
    get_questions_collection,
    create_question,
    list_questions,
    update_question,
    delete_question,
    assign_set,
    override_difficulty,
)
from ..services.question_difficulty import run_difficulty_judging

router = APIRouter(prefix="/questions", tags=["questions"])

def require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user

@router.post("", response_model=QuestionAdminPublic, dependencies=[Depends(require_admin)])
def create_question_endpoint(data: QuestionCreate, request: Request):
    col = get_questions_collection(request.app.state.db)
    return create_question(col, data)

@router.get("", response_model=List[QuestionAdminPublic], dependencies=[Depends(require_admin)])
def list_questions_endpoint(request: Request):
    col = get_questions_collection(request.app.state.db)
    return list_questions(col)

@router.post("/judge-difficulty", dependencies=[Depends(require_admin)])
def judge_difficulty_endpoint(request: Request):
    """Run the AI difficulty pass over all unjudged questions right now,
    using the shared UF LiteLLM gateway client."""
    return run_difficulty_judging(request.app.state.db, get_sync_llm_client())

@router.put("/{question_id}", response_model=QuestionAdminPublic, dependencies=[Depends(require_admin)])
def update_question_endpoint(question_id: str, data: QuestionUpdate, request: Request):
    col = get_questions_collection(request.app.state.db)
    return update_question(col, question_id, data)

@router.patch("/{question_id}/set", response_model=QuestionAdminPublic, dependencies=[Depends(require_admin)])
def assign_set_endpoint(question_id: str, data: SetAssign, request: Request):
    col = get_questions_collection(request.app.state.db)
    return assign_set(col, question_id, data.set)

@router.patch("/{question_id}/difficulty", response_model=QuestionAdminPublic, dependencies=[Depends(require_admin)])
def override_difficulty_endpoint(question_id: str, data: DifficultyOverride, request: Request):
    col = get_questions_collection(request.app.state.db)
    return override_difficulty(col, question_id, data.difficulty)

@router.delete("/{question_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_question_endpoint(question_id: str, request: Request):
    col = get_questions_collection(request.app.state.db)
    delete_question(col, question_id)
    return
