# backend/app/api/surveys.py
from fastapi import APIRouter, Request, Depends, HTTPException
from ..api.auth import get_current_user
from ..schemas.user import UserPublic
from ..services import study_flow
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


def require_survey_access(
    request: Request, user: UserPublic = Depends(get_current_user)
) -> UserPublic:
    """Allow a survey stage only when it is the participant's current step.

    Mirrors require_quiz_access in api/quiz.py — the flow is enforced on the
    server, not just by the page's redirects. Admins are exempt so they can
    inspect any stage.
    """
    stage = request.path_params["stage"]

    if user.is_admin:
        return user

    if not study_flow.is_known_survey_stage(stage):
        raise HTTPException(status_code=400, detail=f"Invalid survey stage: {stage}")

    step_id = study_flow.survey_step_id(stage)

    if step_id not in user.step_order:
        raise HTTPException(
            status_code=403, detail="Survey is not part of your study flow"
        )

    if not study_flow.is_step_unlocked_for(user.step_order, user.completed_steps, step_id):
        raise HTTPException(
            status_code=403, detail="This survey is not your current step"
        )

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
def get_state(stage: str, request: Request, user: UserPublic = Depends(require_survey_access)):
    return build_survey_state(request.app.state.db, user.id, user.email, stage)

@router.post("/{stage}/record_shown")
def record_shown(stage: str, item_id: str, request: Request, user: UserPublic = Depends(require_survey_access)):
    record_item_shown(request.app.state.db, user.id, stage, item_id)
    return {"ok": True}

@router.post("/{stage}/submit", response_model=SurveyStateResponse)
def submit(stage: str, data: SurveySubmitRequest, request: Request, user: UserPublic = Depends(require_survey_access)):
    return submit_survey(request.app.state.db, user.id, user.email, stage, data)
