# backend/app/api/study.py
"""Participant flow endpoints.

GET /study/next is the single authority on where a participant goes next. It
replaces the routing ladders that were previously duplicated across the quiz
page, the survey page, services/quiz.py and services/surveys.py.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from ..schemas.study import (
    NextStepResponse,
    StepPublic,
    StudyConfigPublic,
    StudyConfigUpdate,
    StudyFlowResponse,
)
from ..schemas.question import ALL_SET_IDS
from ..schemas.user import UserPublic
from ..services import study_flow
from .auth import get_current_user

router = APIRouter(prefix="/study", tags=["study"])

# Where participants land once every step is done.
FINISHED_ROUTE = "/dashboard"


def require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def _to_step_public(step: study_flow.Step, completed: bool) -> StepPublic:
    return StepPublic(
        id=step.id,
        kind=step.kind,
        key=step.key,
        label=step.label,
        route=step.route,
        variant=step.variant,
        completed=completed,
    )


@router.get("/next", response_model=NextStepResponse)
def get_next_step(user: UserPublic = Depends(get_current_user)):
    step_order = list(user.step_order)
    completed = set(user.completed_steps)

    step_id = study_flow.next_step_id_from(step_order, completed)
    step = study_flow.get_step(step_id) if step_id else None

    return NextStepResponse(
        next_step=_to_step_public(step, False) if step else None,
        next_route=step.route if step else FINISHED_ROUTE,
        completed_count=len([s for s in step_order if s in completed]),
        total_steps=len(step_order),
        finished=step is None,
    )


@router.get("/flow", response_model=StudyFlowResponse)
def get_flow(user: UserPublic = Depends(get_current_user)):
    step_order = list(user.step_order)
    completed = set(user.completed_steps)

    steps = []
    for step_id in step_order:
        step = study_flow.get_step(step_id)
        if step:
            steps.append(_to_step_public(step, step_id in completed))

    current = study_flow.next_step_id_from(step_order, completed)

    return StudyFlowResponse(
        steps=steps,
        variant_sequence=list(user.variant_sequence),
        current_step_id=current,
        completed_count=len([s for s in step_order if s in completed]),
        total_steps=len(step_order),
        finished=current is None,
        study_flow_version=user.study_flow_version,
    )


# ----- admin: flow ordering -----

def _config_public(config: study_flow.StudyConfig) -> StudyConfigPublic:
    # Worked example of the orders participants will actually be handed, so the
    # admin can see the effect of a change before saving it.
    if config.counterbalance and config.mode == study_flow.MODE_ALL_VARIANTS:
        preview = [
            study_flow.variant_sequence_for_seq(seq, config)
            for seq in range(1, len(config.variant_order) + 1)
        ]
    elif config.mode == study_flow.MODE_SINGLE_VARIANT:
        preview = [
            study_flow.variant_sequence_for_seq(seq, config)[:1]
            for seq in range(1, len(config.variant_order) + 1)
        ]
    else:
        preview = [list(config.variant_order)]

    # The quizzes a participant can be handed, base first, then each variant —
    # the order the admin will want to map sets in.
    known_quiz_ids = [study_flow.BASE_QUIZ_ID, *study_flow.all_variants()]

    return StudyConfigPublic(
        mode=config.mode,
        variant_order=list(config.variant_order),
        counterbalance=config.counterbalance,
        version=config.version,
        known_variants=study_flow.all_variants(),
        variant_labels={v: study_flow.variant_label(v) for v in study_flow.all_variants()},
        preview=preview,
        quiz_set_mode=config.quiz_set_mode,
        quiz_set_map=study_flow.quiz_set_map_dict(config),
        known_sets=list(ALL_SET_IDS),
        known_quiz_ids=known_quiz_ids,
        quiz_labels={
            q: (step.label if (step := study_flow.get_step(study_flow.quiz_step_id(q))) else q)
            for q in known_quiz_ids
        },
    )


@router.get("/config", response_model=StudyConfigPublic)
def get_config(request: Request, user: UserPublic = Depends(require_admin)):
    db = request.app.state.db
    return _config_public(study_flow.load_study_config(db))


@router.put("/config", response_model=StudyConfigPublic)
def update_config(
    data: StudyConfigUpdate,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    db = request.app.state.db

    if data.variant_order is not None:
        known = set(study_flow.all_variants())
        unknown = [v for v in data.variant_order if v not in known]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown variant(s): {', '.join(unknown)}",
            )

    if data.quiz_set_map is not None:
        # Reject rather than silently reconciling, so a typo in the admin UI is
        # visible instead of quietly leaving a quiz unmapped.
        unknown_quizzes = [
            q for q in data.quiz_set_map if not study_flow.is_known_quiz_id(q)
        ]
        if unknown_quizzes:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown quiz(zes): {', '.join(sorted(unknown_quizzes))}",
            )

        unknown_sets = sorted(
            {s for s in data.quiz_set_map.values() if s not in ALL_SET_IDS}
        )
        if unknown_sets:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown set(s): {', '.join(unknown_sets)}",
            )

        duplicates = sorted(
            {s for s in data.quiz_set_map.values()
             if list(data.quiz_set_map.values()).count(s) > 1}
        )
        if duplicates:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Each quiz needs its own set, or questions can repeat across "
                    f"quizzes. Set(s) used more than once: {', '.join(duplicates)}"
                ),
            )

    config = study_flow.save_study_config(
        db,
        mode=data.mode,
        variant_order=data.variant_order,
        counterbalance=data.counterbalance,
        quiz_set_mode=data.quiz_set_mode,
        quiz_set_map=data.quiz_set_map,
    )
    return _config_public(config)
