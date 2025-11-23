from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from ..schemas.question import QuestionCreate, QuestionPublic, QuestionUpdate
from ..schemas.user import UserPublic
from .auth import get_current_user
from ..services.questions import (
    get_questions_collection,
    create_question,
    list_questions,
    update_question,
    delete_question,
)

router = APIRouter(prefix="/questions", tags=["questions"])

def require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user

@router.post("", response_model=QuestionPublic, dependencies=[Depends(require_admin)])
def create_question_endpoint(data: QuestionCreate, request: Request):
    col = get_questions_collection(request.app.state.db)
    return create_question(col, data)

@router.get("", response_model=List[QuestionPublic], dependencies=[Depends(require_admin)])
def list_questions_endpoint(request: Request):
    col = get_questions_collection(request.app.state.db)
    return list_questions(col)

@router.put("/{question_id}", response_model=QuestionPublic, dependencies=[Depends(require_admin)])
def update_question_endpoint(question_id: str, data: QuestionUpdate, request: Request):
    col = get_questions_collection(request.app.state.db)
    return update_question(col, question_id, data)

@router.delete("/{question_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_question_endpoint(question_id: str, request: Request):
    col = get_questions_collection(request.app.state.db)
    delete_question(col, question_id)
    return