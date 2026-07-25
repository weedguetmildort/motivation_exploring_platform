# backend/app/api/users.py
from fastapi import APIRouter, Depends, HTTPException, Request
from bson import ObjectId
from bson.errors import InvalidId

from ..schemas.user import (
    UserPublic,
    ParticipantSummary,
    AssignedVar,
    SurveyStage,
    NextAssignment,
    NextAssignmentUpdate,
    QuizDefaultSets,
    ParticipantSetsUpdate,
    FollowupStudyUpdate,
)
from ..api.auth import get_current_user
from ..services.users import (
    get_users_collection,
    peek_next_assignment,
    set_next_assignment_override,
    get_quiz_default_sets,
    set_quiz_default_sets,
    set_participant_quiz_sets,
    set_participant_followup_study,
)

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
        quiz_sets=doc.get("quiz_sets"),
        followup_study_granted=doc.get("followup_study_granted", False),
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


# NOTE: these must be declared before "/{user_id}" or that route would capture
# "next-assignment" as a user_id (→ InvalidId → 404).
@router.get("/next-assignment", response_model=NextAssignment)
def get_next_assignment(
    request: Request,
    _: UserPublic = Depends(_require_admin),
):
    col = get_users_collection(request.app.state.db)
    return peek_next_assignment(col)


@router.put("/next-assignment", response_model=NextAssignment)
def put_next_assignment(
    body: NextAssignmentUpdate,
    request: Request,
    _: UserPublic = Depends(_require_admin),
):
    col = get_users_collection(request.app.state.db)
    variant = body.variant.value if body.variant is not None else None
    set_next_assignment_override(col, variant)
    return peek_next_assignment(col)


# Also static — must precede "/{user_id}" for the same reason as next-assignment.
@router.get("/quiz-default-sets", response_model=QuizDefaultSets)
def get_quiz_default_sets_endpoint(
    request: Request,
    _: UserPublic = Depends(_require_admin),
):
    col = get_users_collection(request.app.state.db)
    return QuizDefaultSets(sets=get_quiz_default_sets(col))


@router.put("/quiz-default-sets", response_model=QuizDefaultSets)
def put_quiz_default_sets(
    body: QuizDefaultSets,
    request: Request,
    _: UserPublic = Depends(_require_admin),
):
    col = get_users_collection(request.app.state.db)
    set_quiz_default_sets(col, body.sets)
    return QuizDefaultSets(sets=get_quiz_default_sets(col))


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


@router.patch("/{user_id}/quiz-sets", response_model=ParticipantSummary)
def patch_participant_quiz_sets(
    user_id: str,
    body: ParticipantSetsUpdate,
    request: Request,
    _: UserPublic = Depends(_require_admin),
):
    try:
        ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Participant not found")
    col = get_users_collection(request.app.state.db)
    updated = set_participant_quiz_sets(col, user_id, body.quiz_sets)
    if not updated:
        raise HTTPException(status_code=404, detail="Participant not found")
    return _to_summary(updated)


@router.patch("/{user_id}/followup-study", response_model=ParticipantSummary)
def patch_participant_followup_study(
    user_id: str,
    body: FollowupStudyUpdate,
    request: Request,
    _: UserPublic = Depends(_require_admin),
):
    try:
        ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=404, detail="Participant not found")
    col = get_users_collection(request.app.state.db)
    updated = set_participant_followup_study(col, user_id, body.granted)
    if not updated:
        raise HTTPException(status_code=404, detail="Participant not found")
    return _to_summary(updated)
