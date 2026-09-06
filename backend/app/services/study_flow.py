# backend/app/services/study_flow.py
"""
Single source of truth for the participant study flow.

Design (Option C - code catalog + DB ordering):

  * WHAT a step is lives in code (STEP_REGISTRY). A step knows its route, the
    quiz_id / survey stage it drives, and where its survey questions come from.
    This has to be code because the chat variants are real endpoints
    (see api/chat.py: /chat/double, /chat/followup, /chat/links).

  * WHAT ORDER the steps run in lives in one small Mongo doc
    (study_config/active_flow), editable by an admin, falling back to the code
    defaults below when absent. Admins can reorder variants, pin a fixed order,
    or switch back to the legacy one-variant-per-user mode.

  * Each user gets their resolved step_order SNAPSHOTTED onto their user doc at
    signup. An admin reordering mid-study therefore only affects participants
    who sign up afterwards; in-flight users keep a coherent sequence.

Adding or removing a chatbot variant is a one-line change to AssignedVar in
schemas/user.py - the registry, the flow, and the round-robin all expand or
contract to match, with no DB edit required.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Literal, Optional

from bson.objectid import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection

from ..schemas.user import AssignedVar, SurveyStage

# ---------------------------------------------------------------------------
# Step catalog
# ---------------------------------------------------------------------------

StepKind = Literal["quiz", "survey"]

BASE_QUIZ_ID = "base"

# The base quiz is always first - it is the no-variant baseline measurement.
BASE_FIRST = True

# Survey stage whose *questions* every post-variant survey reuses.
SHARED_POST_QUESTION_STAGE = SurveyStage.post_base.value

# Legacy response stage used by the old single-variant flow. Still recognised so
# historical survey_responses docs remain readable, but never scheduled.
LEGACY_POST_VARIANT_STAGE = SurveyStage.post_variant.value


@dataclass(frozen=True)
class Step:
    """One stop in the participant flow."""

    id: str                       # e.g. "quiz:base", "survey:post_links"
    kind: StepKind
    key: str                      # quiz_id for quizzes, response stage for surveys
    label: str
    route: str                    # frontend path to send the user to
    question_stage: Optional[str] = None  # surveys: stage the items are read from
    variant: Optional[str] = None         # set for variant quizzes / their surveys


def quiz_step_id(quiz_id: str) -> str:
    return f"quiz:{quiz_id}"


def survey_step_id(stage: str) -> str:
    return f"survey:{stage}"


def post_variant_stage(variant: str) -> str:
    """Response stage for the survey that follows a given variant quiz.

    Each variant needs its OWN response stage: survey_responses is uniquely
    indexed on (user_id, stage), so three interstitial surveys cannot all share
    "post_base" - the second would read back the first's completed document.
    The questions still come from post_base via `question_stage`.
    """
    return f"post_{variant}"


VARIANT_LABELS = {
    AssignedVar.followup.value: "Follow-up Questions",
    AssignedVar.double.value: "Dual Agent",
    AssignedVar.links.value: "Cited Links",
}


def all_variants() -> list[str]:
    """Every variant the code currently knows about, in declaration order."""
    return [v.value for v in AssignedVar]


def variant_label(variant: str) -> str:
    return VARIANT_LABELS.get(variant, variant.replace("_", " ").title())


def _build_registry() -> dict[str, Step]:
    steps: dict[str, Step] = {}

    steps[survey_step_id(SurveyStage.pre_base.value)] = Step(
        id=survey_step_id(SurveyStage.pre_base.value),
        kind="survey",
        key=SurveyStage.pre_base.value,
        label="Pre-Quiz Survey",
        route=f"/survey?stage={SurveyStage.pre_base.value}",
        question_stage=SurveyStage.pre_base.value,
    )

    steps[quiz_step_id(BASE_QUIZ_ID)] = Step(
        id=quiz_step_id(BASE_QUIZ_ID),
        kind="quiz",
        key=BASE_QUIZ_ID,
        label="Base Quiz",
        route=f"/quiz/{BASE_QUIZ_ID}",
    )

    steps[survey_step_id(SurveyStage.post_base.value)] = Step(
        id=survey_step_id(SurveyStage.post_base.value),
        kind="survey",
        key=SurveyStage.post_base.value,
        label="Post-Base Quiz Survey",
        route=f"/survey?stage={SurveyStage.post_base.value}",
        question_stage=SurveyStage.post_base.value,
    )

    for variant in all_variants():
        label = variant_label(variant)

        steps[quiz_step_id(variant)] = Step(
            id=quiz_step_id(variant),
            kind="quiz",
            key=variant,
            label=f"{label} Quiz",
            route=f"/quiz/{variant}",
            variant=variant,
        )

        stage = post_variant_stage(variant)
        steps[survey_step_id(stage)] = Step(
            id=survey_step_id(stage),
            kind="survey",
            key=stage,
            label=f"Post-{label} Survey",
            route=f"/survey?stage={stage}",
            question_stage=SHARED_POST_QUESTION_STAGE,
            variant=variant,
        )

    # Legacy stage from the single-variant flow. Readable, never scheduled.
    steps[survey_step_id(LEGACY_POST_VARIANT_STAGE)] = Step(
        id=survey_step_id(LEGACY_POST_VARIANT_STAGE),
        kind="survey",
        key=LEGACY_POST_VARIANT_STAGE,
        label="Final Survey",
        route=f"/survey?stage={LEGACY_POST_VARIANT_STAGE}",
        question_stage=SHARED_POST_QUESTION_STAGE,
    )

    return steps


STEP_REGISTRY: dict[str, Step] = _build_registry()


def get_step(step_id: str) -> Optional[Step]:
    return STEP_REGISTRY.get(step_id)


def survey_question_stage(stage: str) -> Optional[str]:
    """Where a survey response stage sources its question definitions."""
    step = STEP_REGISTRY.get(survey_step_id(stage))
    return step.question_stage if step else None


def is_known_survey_stage(stage: str) -> bool:
    return survey_step_id(stage) in STEP_REGISTRY


def is_known_quiz_id(quiz_id: str) -> bool:
    return quiz_step_id(quiz_id) in STEP_REGISTRY


# ---------------------------------------------------------------------------
# Flow configuration (DB-backed, code defaults)
# ---------------------------------------------------------------------------

STUDY_CONFIG_ID = "active_flow"

MODE_ALL_VARIANTS = "all_variants"
MODE_SINGLE_VARIANT = "single_variant"  # legacy behaviour, kept as a backup

ROUND_ROBIN_COUNTER_ID = "user_signup_round_robin"


@dataclass(frozen=True)
class StudyConfig:
    mode: str = MODE_ALL_VARIANTS
    # Canonical variant ordering. Rotated per participant when counterbalance
    # is on; used verbatim for everyone when it is off.
    variant_order: tuple[str, ...] = ()
    counterbalance: bool = True
    version: int = 1

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "variant_order": list(self.variant_order),
            "counterbalance": self.counterbalance,
            "version": self.version,
        }


def get_study_config_collection(db) -> Collection:
    return db["study_config"]


def _reconcile_variant_order(stored: Optional[Iterable[str]]) -> tuple[str, ...]:
    """Make a stored ordering agree with the variants the code declares.

    Unknown entries (a variant removed from AssignedVar) are dropped; variants
    the stored list has never seen (a newly added one) are appended. This is why
    adding or removing a variant needs no DB edit.
    """
    known = all_variants()
    known_set = set(known)

    ordered: list[str] = []
    for v in stored or []:
        if v in known_set and v not in ordered:
            ordered.append(v)

    for v in known:
        if v not in ordered:
            ordered.append(v)

    return tuple(ordered)


def load_study_config(db) -> StudyConfig:
    doc = get_study_config_collection(db).find_one({"_id": STUDY_CONFIG_ID}) or {}

    mode = doc.get("mode", MODE_ALL_VARIANTS)
    if mode not in (MODE_ALL_VARIANTS, MODE_SINGLE_VARIANT):
        mode = MODE_ALL_VARIANTS

    return StudyConfig(
        mode=mode,
        variant_order=_reconcile_variant_order(doc.get("variant_order")),
        counterbalance=bool(doc.get("counterbalance", True)),
        version=int(doc.get("version", 1)),
    )


def save_study_config(
    db,
    *,
    mode: Optional[str] = None,
    variant_order: Optional[Iterable[str]] = None,
    counterbalance: Optional[bool] = None,
) -> StudyConfig:
    """Persist an admin flow change and bump the flow version.

    The version is stamped onto every user assigned afterwards, so a mid-study
    reorder stays visible in the data rather than silently splitting the cohort.
    """
    current = load_study_config(db)

    new_mode = mode if mode in (MODE_ALL_VARIANTS, MODE_SINGLE_VARIANT) else current.mode
    new_order = _reconcile_variant_order(
        variant_order if variant_order is not None else current.variant_order
    )
    new_counterbalance = (
        current.counterbalance if counterbalance is None else bool(counterbalance)
    )

    changed = (
        new_mode != current.mode
        or new_order != current.variant_order
        or new_counterbalance != current.counterbalance
    )

    version = current.version + 1 if changed else current.version

    get_study_config_collection(db).update_one(
        {"_id": STUDY_CONFIG_ID},
        {
            "$set": {
                "mode": new_mode,
                "variant_order": list(new_order),
                "counterbalance": new_counterbalance,
                "version": version,
                "updated_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )

    return StudyConfig(
        mode=new_mode,
        variant_order=new_order,
        counterbalance=new_counterbalance,
        version=version,
    )


# ---------------------------------------------------------------------------
# Assignment (round-robin, expanded to whole sequences)
# ---------------------------------------------------------------------------

def next_round_robin_seq(db) -> int:
    """Atomically claim the next round-robin slot. Same counter as before."""
    counters = db["counters"]
    doc = counters.find_one_and_update(
        {"_id": ROUND_ROBIN_COUNTER_ID},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc.get("seq", 1))


def variant_sequence_for_seq(seq: int, config: StudyConfig) -> list[str]:
    """Variant ordering for the participant holding round-robin slot `seq`.

    Counterbalanced mode walks a cyclic Latin square: with N variants there are
    N rotations, and across them each variant lands in each position exactly
    once. That keeps position effects balanced while staying O(N) rather than
    O(N!) - so it still works if the variant list grows or shrinks.

        seq 1: followup, links,    double
        seq 2: links,    double,   followup
        seq 3: double,   followup, links
    """
    variants = list(config.variant_order)
    if not variants:
        return []

    if not config.counterbalance:
        return variants

    n = len(variants)
    offset = (seq - 1) % n
    return [variants[(offset + i) % n] for i in range(n)]


def build_step_order(variant_sequence: Iterable[str]) -> list[str]:
    """Assemble the full step list: intro survey, base quiz, then each variant."""
    steps: list[str] = [survey_step_id(SurveyStage.pre_base.value)]

    if BASE_FIRST:
        steps.append(quiz_step_id(BASE_QUIZ_ID))
        steps.append(survey_step_id(SurveyStage.post_base.value))

    for variant in variant_sequence:
        if not is_known_quiz_id(variant):
            continue
        steps.append(quiz_step_id(variant))
        steps.append(survey_step_id(post_variant_stage(variant)))

    return steps


def assign_flow(db) -> dict:
    """Claim a round-robin slot and resolve this participant's whole flow."""
    config = load_study_config(db)
    seq = next_round_robin_seq(db)

    sequence = variant_sequence_for_seq(seq, config)

    if config.mode == MODE_SINGLE_VARIANT:
        # Legacy backup: one variant per participant, exactly as before.
        sequence = sequence[:1]

    step_order = build_step_order(sequence)

    return {
        "step_order": step_order,
        "variant_sequence": sequence,
        # assigned_var stays populated (first variant) so existing queries,
        # analytics, and admin views keep working unchanged.
        "assigned_var": sequence[0] if sequence else AssignedVar.followup.value,
        "study_flow_version": config.version,
        "study_flow_mode": config.mode,
        "round_robin_seq": seq,
    }


# ---------------------------------------------------------------------------
# Per-user progress
# ---------------------------------------------------------------------------

def _legacy_backfill_completed(doc: dict, step_order: list[str]) -> list[str]:
    """Reconstruct completed_steps for a user created before this flow existed."""
    assigned = doc.get("assigned_var") or AssignedVar.followup.value
    completed: list[str] = []

    def mark(step_id: str) -> None:
        if step_id in step_order and step_id not in completed:
            completed.append(step_id)

    if doc.get("survey_pre_base_completed"):
        mark(survey_step_id(SurveyStage.pre_base.value))
    if doc.get("quiz_base_completed"):
        mark(quiz_step_id(BASE_QUIZ_ID))
    if doc.get("survey_post_base_completed"):
        mark(survey_step_id(SurveyStage.post_base.value))
    if doc.get("quiz_variant_completed"):
        mark(quiz_step_id(assigned))
    if doc.get("survey_post_variant_completed"):
        # Their answers live under the legacy "post_variant" response stage.
        # Marking the new per-variant step complete means they are never asked
        # again, and the original response document is left untouched for
        # analysis rather than migrated.
        mark(survey_step_id(post_variant_stage(assigned)))

    return completed


def ensure_user_flow(db, doc: dict) -> dict:
    """Guarantee the user doc carries a step_order / completed_steps pair.

    Users created before this change are backfilled in place, on first read,
    from their legacy boolean flags. Their assigned variant stays first so an
    in-flight participant continues where they left off.
    """
    if doc.get("step_order"):
        if doc.get("completed_steps") is None:
            completed = _legacy_backfill_completed(doc, list(doc["step_order"]))
            db["users"].update_one(
                {"_id": doc["_id"]}, {"$set": {"completed_steps": completed}}
            )
            doc["completed_steps"] = completed
        return doc

    config = load_study_config(db)
    assigned = doc.get("assigned_var") or AssignedVar.followup.value

    variants = list(config.variant_order)
    if assigned in variants:
        # Keep the variant they were already assigned in position one.
        offset = variants.index(assigned)
        sequence = [variants[(offset + i) % len(variants)] for i in range(len(variants))]
    else:
        sequence = variants

    if config.mode == MODE_SINGLE_VARIANT:
        sequence = sequence[:1]

    step_order = build_step_order(sequence)
    completed = _legacy_backfill_completed(doc, step_order)

    update = {
        "step_order": step_order,
        "completed_steps": completed,
        "variant_sequence": sequence,
        "study_flow_version": config.version,
        "study_flow_mode": config.mode,
        "assigned_var": assigned,
    }
    db["users"].update_one({"_id": doc["_id"]}, {"$set": update})
    doc.update(update)
    return doc


def next_step_id(doc: dict) -> Optional[str]:
    """First step in this user's order that they have not completed."""
    completed = set(doc.get("completed_steps") or [])
    for step_id in doc.get("step_order") or []:
        if step_id not in completed:
            return step_id
    return None


def next_step(doc: dict) -> Optional[Step]:
    step_id = next_step_id(doc)
    return get_step(step_id) if step_id else None


def is_step_unlocked(doc: dict, step_id: str) -> bool:
    """A step is reachable only when it is the user's current next step."""
    return next_step_id(doc) == step_id


def derive_legacy_flags(doc: dict) -> dict:
    """Recompute the old boolean flags from the step list.

    They are no longer used for routing, but they are kept accurate so anything
    querying Mongo directly - analytics, exports, admin views - still reads.
    """
    step_order: list[str] = list(doc.get("step_order") or [])
    completed = set(doc.get("completed_steps") or [])

    def done(step_id: str) -> bool:
        return step_id in completed

    variant_quiz_steps = []
    variant_survey_steps = []
    for s in step_order:
        step = get_step(s)
        if not step or not step.variant:
            continue
        if step.kind == "quiz":
            variant_quiz_steps.append(s)
        elif step.kind == "survey":
            variant_survey_steps.append(s)

    all_variant_quizzes_done = bool(variant_quiz_steps) and all(
        done(s) for s in variant_quiz_steps
    )
    all_variant_surveys_done = bool(variant_survey_steps) and all(
        done(s) for s in variant_survey_steps
    )

    remaining = [s for s in step_order if s not in completed]

    if not remaining:
        stage = SurveyStage.complete.value
    elif not done(quiz_step_id(BASE_QUIZ_ID)):
        stage = SurveyStage.pre_base.value
    elif not done(survey_step_id(SurveyStage.post_base.value)):
        stage = SurveyStage.post_base.value
    else:
        stage = SurveyStage.post_variant.value

    return {
        "survey_pre_base_completed": done(survey_step_id(SurveyStage.pre_base.value)),
        "quiz_base_completed": done(quiz_step_id(BASE_QUIZ_ID)),
        "survey_post_base_completed": done(survey_step_id(SurveyStage.post_base.value)),
        "quiz_variant_completed": all_variant_quizzes_done,
        "survey_post_variant_completed": all_variant_surveys_done,
        "survey_stage": stage,
    }


def mark_step_completed(db, user_id: str, step_id: str, completed_at: datetime) -> dict:
    """Record a finished step and refresh the derived legacy flags."""
    users = db["users"]
    doc = users.find_one({"_id": ObjectId(user_id)})
    if not doc:
        return {}

    doc = ensure_user_flow(db, doc)

    completed = list(doc.get("completed_steps") or [])
    if step_id in (doc.get("step_order") or []) and step_id not in completed:
        completed.append(step_id)

    doc["completed_steps"] = completed

    update = {"completed_steps": completed, "updated_at": completed_at}
    update.update(derive_legacy_flags(doc))

    users.update_one({"_id": doc["_id"]}, {"$set": update})
    return update


def unmark_step_completed(db, user_id: str, step_id: str) -> dict:
    """Reverse of mark_step_completed - used by the admin reset endpoints."""
    users = db["users"]
    doc = users.find_one({"_id": ObjectId(user_id)})
    if not doc:
        return {}

    doc = ensure_user_flow(db, doc)

    completed = [s for s in (doc.get("completed_steps") or []) if s != step_id]
    doc["completed_steps"] = completed

    update = {"completed_steps": completed, "updated_at": datetime.utcnow()}
    update.update(derive_legacy_flags(doc))

    users.update_one({"_id": doc["_id"]}, {"$set": update})
    return update
