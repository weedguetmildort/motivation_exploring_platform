# backend/app/api/users.py
from fastapi import APIRouter, Depends, HTTPException, Request
from bson import ObjectId
from bson.errors import InvalidId

from ..schemas.user import UserPublic, ParticipantSummary, AssignedVar, SurveyStage
from ..api.auth import get_current_user
from ..services.users import get_users_collection

router = APIRouter(prefix="/users", tags=["users"])


def _require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _safe_survey_stage(raw: str | None) -> SurveyStage:
    valid = {e.value for e in SurveyStage}
    return SurveyStage(raw) if raw in valid else SurveyStage.pre_base


def _to_summary(doc: dict) -> ParticipantSummary:
    return ParticipantSummary(
        id=str(doc["_id"]),
        email=doc["email"],
        first_name=doc.get("first_name"),
        last_name=doc.get("last_name"),
        assigned_var=doc.get("assigned_var", AssignedVar.followup.value),
        survey_stage=_safe_survey_stage(doc.get("survey_stage")),
        demographics_completed=doc.get("demographics_completed", False),
        survey_pre_base_completed=doc.get("survey_pre_base_completed", False),
        quiz_base_completed=doc.get("quiz_base_completed", False),
        survey_post_base_completed=doc.get("survey_post_base_completed", False),
        quiz_variant_completed=doc.get("quiz_variant_completed", False),
        survey_post_variant_completed=doc.get("survey_post_variant_completed", False),
        last_active_at=doc.get("last_active_at"),
        consent_declined_at=doc.get("consent_declined_at"),
        consent_viewed_at=doc.get("consent_viewed_at"),
        consent_abandoned_at=doc.get("consent_abandoned_at"),
        created_at=doc.get("created_at"),
    )


@router.get("", response_model=list[ParticipantSummary])
def list_participants(
    request: Request,
    _: UserPublic = Depends(_require_admin),
):
    col = get_users_collection(request.app.state.db)
    docs = list(col.find({"is_admin": False}, sort=[("created_at", -1)]))
    return [_to_summary(doc) for doc in docs]


@router.get("/{user_id}", response_model=ParticipantSummary)
def get_participant(
    user_id: str,
    request: Request,
    _: UserPublic = Depends(_require_admin),
):
    try:
        oid = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Participant not found")
    col = get_users_collection(request.app.state.db)
    doc = col.find_one({"_id": oid, "is_admin": False})
    if not doc:
        raise HTTPException(status_code=404, detail="Participant not found")
    return _to_summary(doc)
