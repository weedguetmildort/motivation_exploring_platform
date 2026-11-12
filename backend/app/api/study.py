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
from ..core.study_profiles import profile_for, study_id_of
from ..services.users import get_quiz_default_sets
from ..schemas.user import UserPublic
from ..services import study_flow
from ..services.studies import access_policy
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
def get_flow(request: Request, user: UserPublic = Depends(get_current_user)):
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
        # The participant's frozen protocol, else the study's fixed quiz structure.
        mode=(user.study_protocol or {}).get("mode")
        or study_flow.study_profile_mode(request.app.state.db)
        or study_flow.MODE_ALL_VARIANTS,
    )


# ----- admin: flow ordering -----

def _default_question_sets(db):
    """Study 1 stamps this restriction on new sign-ups; Study 2 enrollments never carry one."""
    return get_quiz_default_sets(db["users"]) if study_id_of(db, "study-1") == "study-1" else None


def _supply_problems(db, *, mode, quiz_set_mode, quiz_set_map, questions_per_quiz, counts=None):
    return study_flow.question_supply_problems(
        mode=mode, quiz_set_mode=quiz_set_mode, quiz_set_map=quiz_set_map, questions_per_quiz=questions_per_quiz,
        counts=counts if counts is not None else study_flow.question_set_counts(db),
        default_sets=_default_question_sets(db))


def _config_public(config: study_flow.StudyConfig, db, applied_participants=None) -> StudyConfigPublic:
    policy = access_policy()
    study_id = study_id_of(db)
    counts = study_flow.question_set_counts(db)
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
        study_id=study_id,
        survey_stages=study_flow.survey_stage_settings(config.survey_stages),
        variant_survey_mode=config.variant_survey_mode,
        mode=config.mode,
        variant_order=list(config.variant_order),
        counterbalance=config.counterbalance,
        version=config.version,
        questions_per_quiz=config.questions_per_quiz,
        wrong_ai_count=config.wrong_ai_count,
        wrong_ai_rate=config.wrong_ai_rate,
        requires_study1_completion=policy["requires_study1_completion"],
        requires_study2_approval=policy["requires_approval"],
        study_access_mode=policy["mode"],
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
        default_quiz_set_mode=profile_for(db).get("quiz_set_mode"),
        question_counts=counts,
        default_question_sets=_default_question_sets(db),
        supply_problems=_supply_problems(
            db, mode=config.mode, quiz_set_mode=config.quiz_set_mode, quiz_set_map=study_flow.quiz_set_map_dict(config),
            questions_per_quiz=config.questions_per_quiz, counts=counts),
        enrolled_with_unstarted_quizzes=study_flow.enrolled_with_unstarted_quizzes(db),
        applied_participants=applied_participants,
    )


@router.get("/config", response_model=StudyConfigPublic)
def get_config(request: Request, user: UserPublic = Depends(require_admin)):
    db = request.app.state.db
    return _config_public(study_flow.load_study_config(db), db)


@router.put("/config", response_model=StudyConfigPublic)
def update_config(
    data: StudyConfigUpdate,
    request: Request,
    user: UserPublic = Depends(require_admin),
):
    db = request.app.state.db

    profile_mode = study_flow.study_profile_mode(db)
    if data.mode is not None and profile_mode and data.mode != profile_mode:
        raise HTTPException(400, "Study 1 uses the base and one variant; Study 2 uses the base and all variants")
    if data.survey_stages is not None:
        unknown = set(data.survey_stages) - set(study_flow.survey_stage_settings())
        if unknown:
            raise HTTPException(400, "Unknown survey stages: " + ", ".join(sorted(unknown)))
        if any(not settings.name.strip() for settings in data.survey_stages.values()):
            raise HTTPException(400, "Survey names cannot be blank")

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

    # Quizzes may share a set: a participant never sees a question twice in a
    # study. Refuse question settings that cannot give every participant
    # different questions in every quiz. Other edits are not blocked by a bank
    # that shrank since; the page shows that problem instead.
    current = study_flow.load_study_config(db)
    saved_supply = dict(mode=current.mode, quiz_set_mode=current.quiz_set_mode,
                        quiz_set_map=study_flow.quiz_set_map_dict(current), questions_per_quiz=current.questions_per_quiz)
    supply = dict(mode=profile_mode or data.mode or current.mode,
                  quiz_set_mode=data.quiz_set_mode or current.quiz_set_mode,
                  quiz_set_map=data.quiz_set_map if data.quiz_set_map is not None else saved_supply["quiz_set_map"],
                  questions_per_quiz=data.questions_per_quiz or current.questions_per_quiz)
    if supply != saved_supply and (problems := _supply_problems(db, **supply)):
        raise HTTPException(400, "Not enough questions to give every participant different questions in each quiz. "
                                 + " ".join(problems))

    config = study_flow.save_study_config(
        db,
        mode=data.mode,
        questions_per_quiz=data.questions_per_quiz,
        wrong_ai_count=data.wrong_ai_count,
        wrong_ai_rate=data.wrong_ai_rate,
        wrong_ai_rate_supplied="wrong_ai_rate" in data.model_fields_set,
        # Ignore the legacy access field from older clients. The deployment
        # policy applies to both existing and future enrollments.
        variant_order=data.variant_order,
        counterbalance=data.counterbalance,
        quiz_set_mode=data.quiz_set_mode,
        quiz_set_map=data.quiz_set_map,
        variant_survey_mode=data.variant_survey_mode,
        survey_stages={key: value.model_dump() for key, value in data.survey_stages.items()} if data.survey_stages is not None else None,
    )
    applied = study_flow.apply_quiz_sets_to_enrolled(db, config, user.id) if data.apply_to_enrolled else None
    return _config_public(config, db, applied)
