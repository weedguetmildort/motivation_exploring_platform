# backend/app/api/surveys.py
from fastapi import APIRouter, Request, Depends, HTTPException
from ..api.auth import get_current_user
from ..schemas.user import UserPublic
from ..schemas.survey import (
    SurveyItemCreate,
    SurveyItemUpdate,
    SurveyItemPublic,
    SurveyStateResponse,
    SurveySubmitRequest,
)
from ..services.surveys import (
    create_survey_item,
    list_survey_items,
    update_survey_item,
    delete_survey_item,
    build_survey_state,
    submit_survey,
    record_item_shown,
)

router = APIRouter(prefix="/surveys", tags=["surveys"])

def require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# ----- admin CRUD -----

@router.post("/items", response_model=SurveyItemPublic)
def admin_create_item(data: SurveyItemCreate, request: Request, user: UserPublic = Depends(require_admin)):
    return create_survey_item(request.app.state.db, data)

@router.get("/items", response_model=list[SurveyItemPublic])
def admin_list_items(request: Request, stage: str | None = None, user: UserPublic = Depends(require_admin)):
    return list_survey_items(request.app.state.db, stage=stage, active_only=False)

@router.put("/items/{item_id}", response_model=SurveyItemPublic)
def admin_update_item(item_id: str, patch: SurveyItemUpdate, request: Request, user: UserPublic = Depends(require_admin)):
    return update_survey_item(request.app.state.db, item_id, patch)

@router.delete("/items/{item_id}")
def admin_delete_item(item_id: str, request: Request, user: UserPublic = Depends(require_admin)):
    delete_survey_item(request.app.state.db, item_id)
    return {"ok": True}

# ----- user flow -----

@router.get("/{stage}/state", response_model=SurveyStateResponse)
def get_state(stage: str, request: Request, user: UserPublic = Depends(get_current_user)):
    return build_survey_state(request.app.state.db, user.id, user.email, stage)

@router.post("/{stage}/record_shown")
def record_shown(stage: str, item_id: str, request: Request, user: UserPublic = Depends(get_current_user)):
    record_item_shown(request.app.state.db, user.id, stage, item_id)
    return {"ok": True}

@router.post("/{stage}/submit", response_model=SurveyStateResponse)
def submit(stage: str, data: SurveySubmitRequest, request: Request, user: UserPublic = Depends(get_current_user)):
    return submit_survey(request.app.state.db, user.id, user.email, stage, data)
