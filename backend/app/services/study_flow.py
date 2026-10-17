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

Scope: this governs the MAIN study only. The Phase 13 follow-up study
(services/quiz.QUIZ2_QUIZ_IDS - base2/followup2/links2/double2) is a separate,
admin-granted track and is deliberately absent from STEP_REGISTRY, so its
attempts fall through every flow check as "not part of this user's flow".
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Literal, Optional

from bson.objectid import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection

from ..schemas.question import ALL_SET_IDS
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

# How each quiz's question set is chosen.
#   preset - a fixed quiz -> set map, the same for every participant
#   random - a per-participant random assignment of sets to that participant's
#            quizzes, snapshotted at signup
#   balanced_random - randomized blocks of set rotations within each quiz order
QUIZ_SET_MODE_PRESET = "preset"
QUIZ_SET_MODE_RANDOM = "random"
QUIZ_SET_MODE_BALANCED_RANDOM = "balanced_random"
QUIZ_SET_MODES = (
    QUIZ_SET_MODE_PRESET, QUIZ_SET_MODE_RANDOM, QUIZ_SET_MODE_BALANCED_RANDOM,
)


@dataclass(frozen=True)
class StudyConfig:
    mode: str = MODE_ALL_VARIANTS
    # Canonical variant ordering. Rotated per participant when counterbalance
    # is on; used verbatim for everyone when it is off.
    variant_order: tuple[str, ...] = ()
    counterbalance: bool = True
    version: int = 1
    questions_per_quiz: int = 5
    wrong_ai_count: int = 3
    wrong_ai_rate: Optional[float] = None
    requires_study1_completion: bool = True
    survey_stages: tuple[tuple[str, str, bool], ...] = ()

    # Which question set each quiz draws from. Giving every quiz its own set is
    # what stops a participant seeing the same question twice across their four
    # quizzes — isolation is structural rather than filtered after the fact.
    quiz_set_mode: str = QUIZ_SET_MODE_BALANCED_RANDOM
    # ((quiz_id, set_letter), ...) — a tuple of pairs rather than a dict because
    # this dataclass is frozen and must stay hashable. Stored in Mongo as a
    # plain object. A quiz absent from the map draws from the whole pool.
    quiz_set_map: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "variant_order": list(self.variant_order),
            "counterbalance": self.counterbalance,
            "version": self.version,
            "questions_per_quiz": self.questions_per_quiz,
            "wrong_ai_count": self.wrong_ai_count,
            "wrong_ai_rate": self.wrong_ai_rate,
            "requires_study1_completion": self.requires_study1_completion,
            "survey_stages": survey_stage_settings(self.survey_stages),
            "quiz_set_mode": self.quiz_set_mode,
            "quiz_set_map": dict(self.quiz_set_map),
        }


def get_study_config_collection(db) -> Collection:
    return db["study_config"]


def survey_stage_settings(stored=None) -> dict:
    """Stable survey IDs; names are administrative and never participant labels."""
    supplied = stored if isinstance(stored, dict) else {key: {"name": name, "enabled": enabled} for key, name, enabled in (stored or ())}
    return {step.key: {"name": (supplied.get(step.key, {}).get("name") or step.label).strip(),
                       "enabled": supplied.get(step.key, {}).get("enabled", True)}
            for step in STEP_REGISTRY.values() if step.kind == "survey" and step.key != LEGACY_POST_VARIANT_STAGE}


def _survey_stage_tuple(stored=None):
    return tuple((key, value["name"], value["enabled"]) for key, value in survey_stage_settings(stored).items())


def study_profile_mode(db):
    sid = getattr(db, "study_id", None)
    return MODE_SINGLE_VARIANT if sid == "study-1" else MODE_ALL_VARIANTS if sid == "study-2" else None


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


def _reconcile_quiz_set_map(
    stored: Optional[dict | Iterable[tuple[str, str]]],
) -> tuple[tuple[str, str], ...]:
    """Drop map entries the code no longer recognises.

    Mirrors _reconcile_variant_order: an entry naming a quiz that is no longer
    in the registry (a retired variant) or a set letter that is no longer in
    SetId is discarded, so adding or removing either needs no DB edit. Unlike
    variants, nothing is auto-appended — an unmapped quiz deliberately falls
    back to the whole pool rather than being handed an arbitrary set.
    """
    if stored is None:
        return ()

    pairs = stored.items() if isinstance(stored, dict) else stored

    reconciled: list[tuple[str, str]] = []
    seen: set[str] = set()
    for quiz_id, set_id in pairs:
        if quiz_id in seen:
            continue
        if not is_known_quiz_id(quiz_id) or set_id not in ALL_SET_IDS:
            continue
        seen.add(quiz_id)
        reconciled.append((quiz_id, set_id))

    return tuple(reconciled)


def quiz_set_map_dict(config: StudyConfig) -> dict[str, str]:
    """The configured quiz -> set map as a plain dict."""
    return dict(config.quiz_set_map)


def load_study_config(db) -> StudyConfig:
    doc = get_study_config_collection(db).find_one({"_id": STUDY_CONFIG_ID}) or {}

    mode = doc.get("mode", MODE_ALL_VARIANTS)
    if mode not in (MODE_ALL_VARIANTS, MODE_SINGLE_VARIANT):
        mode = MODE_ALL_VARIANTS
    mode = study_profile_mode(db) or mode

    quiz_set_mode = doc.get("quiz_set_mode", QUIZ_SET_MODE_BALANCED_RANDOM)
    if quiz_set_mode not in QUIZ_SET_MODES:
        quiz_set_mode = QUIZ_SET_MODE_BALANCED_RANDOM

    return StudyConfig(
        mode=mode,
        variant_order=_reconcile_variant_order(doc.get("variant_order")),
        counterbalance=bool(doc.get("counterbalance", True)),
        version=int(doc.get("version", 1)),
        questions_per_quiz=int(doc.get("questions_per_quiz", 10 if getattr(db, "study_id", None) == "study-1" else 5)),
        wrong_ai_count=int(doc.get("wrong_ai_count", 3)),
        wrong_ai_rate=doc.get("wrong_ai_rate"),
        requires_study1_completion=bool(doc.get("requires_study1_completion", True)),
        survey_stages=_survey_stage_tuple(doc.get("survey_stages")),
        quiz_set_mode=quiz_set_mode,
        quiz_set_map=_reconcile_quiz_set_map(doc.get("quiz_set_map")),
    )


def save_study_config(
    db,
    *,
    mode: Optional[str] = None,
    questions_per_quiz: Optional[int] = None,
    wrong_ai_count: Optional[int] = None,
    wrong_ai_rate: Optional[float] = None,
    wrong_ai_rate_supplied: bool = False,
    requires_study1_completion: Optional[bool] = None,
    variant_order: Optional[Iterable[str]] = None,
    counterbalance: Optional[bool] = None,
    quiz_set_mode: Optional[str] = None,
    quiz_set_map: Optional[dict | Iterable[tuple[str, str]]] = None,
    survey_stages: Optional[dict] = None,
) -> StudyConfig:
    """Persist an admin flow change and bump the flow version.

    The version is stamped onto every user assigned afterwards, so a mid-study
    reorder stays visible in the data rather than silently splitting the cohort.
    """
    current = load_study_config(db)
    if mode is not None and study_profile_mode(db) and mode != study_profile_mode(db):
        raise ValueError("The quiz structure is fixed for this study")

    new_mode = mode if mode in (MODE_ALL_VARIANTS, MODE_SINGLE_VARIANT) else current.mode
    new_order = _reconcile_variant_order(
        variant_order if variant_order is not None else current.variant_order
    )
    new_counterbalance = (
        current.counterbalance if counterbalance is None else bool(counterbalance)
    )
    new_quiz_set_mode = (
        quiz_set_mode if quiz_set_mode in QUIZ_SET_MODES else current.quiz_set_mode
    )
    new_quiz_set_map = _reconcile_quiz_set_map(
        quiz_set_map if quiz_set_map is not None else current.quiz_set_map
    )

    protocol = dict(questions_per_quiz=current.questions_per_quiz if questions_per_quiz is None else questions_per_quiz,
        wrong_ai_count=current.wrong_ai_count if wrong_ai_count is None else wrong_ai_count,
        wrong_ai_rate=wrong_ai_rate if wrong_ai_rate_supplied else current.wrong_ai_rate,
        requires_study1_completion=current.requires_study1_completion if requires_study1_completion is None else requires_study1_completion)
    new_surveys = _survey_stage_tuple({**survey_stage_settings(current.survey_stages), **(survey_stages or {})})
    if not 1 <= protocol["questions_per_quiz"] <= 100 or not 0 <= protocol["wrong_ai_count"] <= 100:
        raise ValueError("Invalid question or wrong-advice count")
    if protocol["wrong_ai_rate"] is not None and not 0 <= protocol["wrong_ai_rate"] <= 1:
        raise ValueError("Wrong-advice rate must be between zero and one")
    changed = (
        any(getattr(current, key) != value for key, value in protocol.items())
        or         new_mode != current.mode
        or new_order != current.variant_order
        or new_counterbalance != current.counterbalance
        or new_quiz_set_mode != current.quiz_set_mode
        or new_quiz_set_map != current.quiz_set_map
        or new_surveys != current.survey_stages
    )

    version = current.version + 1 if changed else current.version

    get_study_config_collection(db).update_one(
        {"_id": STUDY_CONFIG_ID},
        {
            "$set": {
                **protocol,
                "mode": new_mode,
                "variant_order": list(new_order),
                "counterbalance": new_counterbalance,
                "version": version,
                "quiz_set_mode": new_quiz_set_mode,
                "quiz_set_map": dict(new_quiz_set_map),
                "survey_stages": survey_stage_settings(new_surveys),
                "updated_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )

    return StudyConfig(
        **protocol,
        mode=new_mode,
        variant_order=new_order,
        counterbalance=new_counterbalance,
        version=version,
        quiz_set_mode=new_quiz_set_mode,
        quiz_set_map=new_quiz_set_map,
        survey_stages=new_surveys,
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


def build_step_order(variant_sequence: Iterable[str], survey_stages=None) -> list[str]:
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

    settings = survey_stage_settings(survey_stages)
    return [step for step in steps if not step.startswith("survey:") or settings.get(step.split(":", 1)[1], {}).get("enabled", True)]


def quiz_ids_in_order(step_order: Iterable[str]) -> list[str]:
    """The quiz_ids of a step order, in the order the participant meets them."""
    ids: list[str] = []
    for step_id in step_order:
        step = get_step(step_id)
        if step and step.kind == "quiz":
            ids.append(step.key)
    return ids


def _balanced_quiz_set_assignment(db, config: StudyConfig, quiz_ids: list[str]) -> dict[str, str]:
    """Allocate one randomized block slot, independently for each quiz order.

    Each block contains all rotations of a shuffled set list, in shuffled
    order. Thus every quiz receives every set once per complete block, without
    any participant sharing a set across quizzes. Stratifying by the actual
    quiz order crosses set balance with the existing round-robin rotation,
    including fixed-order, single-variant and admin-override assignments.

    Mongo atomically increments the slot and initializes a persistent seed.
    Deriving the block shuffle from that seed makes it stable across workers
    and restarts. The config version separates cohorts after admin changes.
    """
    if not quiz_ids:
        return {}
    if len(quiz_ids) > len(ALL_SET_IDS):
        raise ValueError("Balanced random requires at least one question set per quiz")

    counter_id = "quiz_sets:balanced_random:" + json.dumps(
        [config.version, quiz_ids, list(ALL_SET_IDS)], separators=(",", ":")
    )
    allocation = db["counters"].find_one_and_update(
        {"_id": counter_id},
        {"$inc": {"seq": 1}, "$setOnInsert": {"seed": uuid.uuid4().hex}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    block, slot = divmod(int(allocation["seq"]) - 1, len(ALL_SET_IDS))
    rng = random.Random(f"{allocation['seed']}:{block}")
    sets = list(ALL_SET_IDS)
    offsets = list(range(len(sets)))
    rng.shuffle(sets)
    rng.shuffle(offsets)
    offset = offsets[slot]
    return {quiz_id: sets[(index + offset) % len(sets)]
            for index, quiz_id in enumerate(quiz_ids)}


def resolve_quiz_set_assignment(
    config: StudyConfig, quiz_ids: Iterable[str], *, db=None
) -> dict[str, str]:
    """Map each of this participant's quizzes to the question set it draws from.

    A quiz absent from the result draws from the whole pool, which is what an
    unmapped quiz did before this existed.

    Random mode independently shuffles sets, so balance holds in expectation.
    Balanced random uses randomized blocks within each quiz order for exact
    set counts across complete blocks. Both are resolved once at signup and
    snapshotted like variant_sequence, preserving in-flight assignments.
    """
    ordered_ids = list(quiz_ids)

    if config.quiz_set_mode == QUIZ_SET_MODE_BALANCED_RANDOM:
        if db is None:
            raise ValueError("Balanced random assignment requires a database")
        return _balanced_quiz_set_assignment(db, config, ordered_ids)

    if config.quiz_set_mode == QUIZ_SET_MODE_RANDOM:
        sets = list(ALL_SET_IDS)
        random.shuffle(sets)
        # zip stops at the shorter side: with fewer sets than quizzes the
        # leftover quizzes stay unmapped and draw from the whole pool.
        return dict(zip(ordered_ids, sets))

    wanted = set(ordered_ids)
    return {q: s for q, s in config.quiz_set_map if q in wanted}


def assign_flow(db, forced_first: Optional[str] = None) -> dict:
    """Resolve this participant's whole flow.

    ``forced_first`` is the admin one-shot assignment override (see
    services/users._consume_next_override). When supplied, that variant is
    pinned to position one and the rest rotate around it. As before, honouring
    an override deliberately does NOT advance the round-robin counter, so normal
    rotation resumes cleanly for the next sign-up.
    """
    config = load_study_config(db)

    if forced_first and forced_first in config.variant_order:
        variants = list(config.variant_order)
        offset = variants.index(forced_first)
        sequence = [variants[(offset + i) % len(variants)] for i in range(len(variants))]
        seq = None
        source = "override"
    else:
        seq = next_round_robin_seq(db)
        sequence = variant_sequence_for_seq(seq, config)
        source = "rotation"

    if config.mode == MODE_SINGLE_VARIANT:
        # Legacy backup: one variant per participant, exactly as before.
        sequence = sequence[:1]

    step_order = build_step_order(sequence, config.survey_stages)

    return {
        "step_order": step_order,
        "variant_sequence": sequence,
        # assigned_var stays populated (first variant) so existing queries,
        # analytics, the participants panel and peek_next_assignment keep
        # working unchanged.
        "assigned_var": sequence[0] if sequence else AssignedVar.followup.value,
        # Which question set each of this participant's quizzes draws from.
        # Resolved from step_order so random mode follows the counterbalanced
        # quiz order rather than the registry's declaration order.
        "quiz_set_assignment": resolve_quiz_set_assignment(
            config, quiz_ids_in_order(step_order), db=db
        ),
        "study_flow_version": config.version,
        "study_flow_mode": config.mode,
        "study_protocol": config.as_dict(),
        "round_robin_seq": seq,
        "assignment_source": source,
        "progress_reconciled_version": 1,
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
    from .study_repair import repair_study1_flow
    doc = repair_study1_flow(db, doc)
    if doc.get("is_admin") and study_profile_mode(db):
        config = load_study_config(db)
        sequence = list(config.variant_order)
        if config.mode == MODE_SINGLE_VARIANT:
            sequence = [doc.get("assigned_var")] if doc.get("assigned_var") in all_variants() else sequence[:1]
        order = build_step_order(sequence, config.survey_stages)
        protocol = config.as_dict()
        if doc.get("step_order") != order or doc.get("study_protocol") != protocol:
            patch = {"step_order": order, "study_protocol": protocol, "study_flow_version": config.version,
                "study_flow_mode": config.mode, "variant_sequence": sequence,
                "assigned_var": sequence[0],
                "completed_steps": [s for s in doc.get("completed_steps", []) if s in order],
                "quiz_set_assignment": {**dict(zip(quiz_ids_in_order(order), ("a", "b", "c", "d"))), **(doc.get("quiz_set_assignment") or {})}}
            patch.update(derive_legacy_flags({**doc, **patch}))
            db["users"].update_one({"_id": doc["_id"]}, {"$set": patch})
            doc = {**doc, **patch}
    if doc.get("step_order"):
        patch: dict = {}

        if doc.get("completed_steps") is None:
            patch["completed_steps"] = _legacy_backfill_completed(
                doc, list(doc["step_order"])
            )

        if doc.get("quiz_set_assignment") is None:
            # Assigned before per-quiz sets existed. Resolve against the flow
            # they already have. Deliberately only when the field is MISSING —
            # this runs on every authenticated request, so it must not cost a
            # config read once the participant has been seen. A participant
            # whose assignment does not cover a quiz picks the map up at draw
            # time instead (services/quiz._load_or_create_attempt).
            patch["quiz_set_assignment"] = resolve_quiz_set_assignment(
                load_study_config(db), quiz_ids_in_order(doc["step_order"]), db=db
            )

        if patch:
            db["users"].update_one({"_id": doc["_id"]}, {"$set": patch})
            doc.update(patch)
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

    step_order = build_step_order(sequence, (doc.get("study_protocol") or {}).get("survey_stages"))
    completed = _legacy_backfill_completed(doc, step_order)

    update = {
        "step_order": step_order,
        "completed_steps": completed,
        "variant_sequence": sequence,
        "quiz_set_assignment": (
            doc["quiz_set_assignment"] if doc.get("quiz_set_assignment") is not None
            else resolve_quiz_set_assignment(config, quiz_ids_in_order(step_order), db=db)
        ),
        "study_flow_version": config.version,
        "study_flow_mode": config.mode,
        "study_protocol": doc.get("study_protocol") or config.as_dict(),
        "assigned_var": assigned,
    }
    db["users"].update_one({"_id": doc["_id"]}, {"$set": update})
    doc.update(update)
    return doc


def reconcile_saved_progress(db, doc: dict) -> dict:
    """Repair old progress snapshots from completed, live result records once.

    Response stages are distinct from their shared question banks. In
    particular, a legacy post_variant response belongs only to assigned_var;
    it must never complete every variant survey. Archived quiz runs are excluded.
    """
    if doc.get("progress_reconciled_version", 0) >= 1:
        return doc

    uid = str(doc["_id"])
    # Retry against a fresh snapshot if another request advances or resets a
    # step while migration is running. Never replace concurrent progress.
    while doc.get("progress_reconciled_version", 0) < 1:
        order = list(doc.get("step_order") or [])
        saved_steps = set()
        for response in db["survey_responses"].find({"user_id": uid, "status": "completed"}):
            stage = response.get("stage")
            if stage == SurveyStage.post_variant.value:
                stage = post_variant_stage(doc.get("assigned_var") or AssignedVar.followup.value)
            if stage:
                saved_steps.add(survey_step_id(stage))
        for attempt in db["quiz_attempts"].find({"user_id": uid, "status": "completed"}):
            if attempt.get("quiz_id"):
                saved_steps.add(quiz_step_id(attempt["quiz_id"]))
        previous = doc.get("completed_steps")
        completed = set(previous or []) | saved_steps
        patch = {
            "completed_steps": [step for step in order if step in completed],
            "progress_reconciled_version": 1,
        }
        patch.update(derive_legacy_flags({**doc, **patch}))
        result = db["users"].update_one(
            {"_id": doc["_id"], "completed_steps": previous,
             "progress_reconciled_version": doc.get("progress_reconciled_version")},
            {"$set": patch},
        )
        if result.matched_count:
            return {**doc, **patch}
        doc = db["users"].find_one({"_id": doc["_id"]})
        if not doc:
            return {}
    return doc


def preset_quiz_set(db, quiz_id: str) -> Optional[str]:
    """The set the current preset map gives ``quiz_id``, if any.

    The fallback for a participant whose stored assignment does not cover this
    quiz — which is everyone assigned before the map was configured, since the
    map starts empty. Read at draw time, so it costs nothing on the request path.

    Both random modes return None: their mapping lives on the participant,
    so there is nothing global to fall back to.
    """
    config = load_study_config(db)
    if config.quiz_set_mode != QUIZ_SET_MODE_PRESET:
        return None
    return quiz_set_map_dict(config).get(quiz_id)


def repoint_quiz_set(db, user_id: str, quiz_id: str) -> Optional[str]:
    """Re-point one quiz at the set the CURRENT config gives it.

    Called when an admin resets a quiz, which means "redo this from scratch" —
    including which set it draws from. Without this, an admin who changes the
    map and then resets would keep drawing from their originally-assigned set
    and see no difference.

    Preset mode only: in random mode the mapping is a per-participant shuffle,
    and re-rolling one quiz in isolation could hand it a set another of their
    quizzes already uses, which is exactly the overlap sets exist to prevent.
    Returns the set now assigned, or None if the quiz is unmapped.
    """
    # Admin test runs and the Phase 13 quiz-2 ids are not part of the mapping.
    if not is_known_quiz_id(quiz_id):
        return None

    config = load_study_config(db)
    if config.quiz_set_mode != QUIZ_SET_MODE_PRESET:
        doc = db["users"].find_one({"_id": ObjectId(user_id)}) or {}
        return (doc.get("quiz_set_assignment") or {}).get(quiz_id)

    users = db["users"]
    doc = users.find_one({"_id": ObjectId(user_id)})
    if not doc:
        return None

    assignment = dict(doc.get("quiz_set_assignment") or {})
    new_set = quiz_set_map_dict(config).get(quiz_id)

    if new_set:
        assignment[quiz_id] = new_set
    else:
        assignment.pop(quiz_id, None)

    if assignment != (doc.get("quiz_set_assignment") or {}):
        users.update_one(
            {"_id": doc["_id"]}, {"$set": {"quiz_set_assignment": assignment}}
        )

    return new_set


def next_step_id_from(
    step_order: Optional[Iterable[str]], completed_steps: Optional[Iterable[str]]
) -> Optional[str]:
    """First step in ``step_order`` not present in ``completed_steps``.

    Takes the two lists directly so callers holding a UserPublic (which carries
    both) don't need to re-read the Mongo document.
    """
    completed = set(completed_steps or [])
    for step_id in step_order or []:
        if step_id not in completed:
            return step_id
    return None


def next_step_id(doc: dict) -> Optional[str]:
    """First step in this user's order that they have not completed."""
    return next_step_id_from(doc.get("step_order"), doc.get("completed_steps"))


def is_step_unlocked_for(
    step_order: Optional[Iterable[str]],
    completed_steps: Optional[Iterable[str]],
    step_id: str,
) -> bool:
    """A step is reachable only when it is the current next step."""
    return next_step_id_from(step_order, completed_steps) == step_id


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
    all_variant_surveys_done = all(
        done(s) for s in variant_survey_steps
    )

    remaining = [s for s in step_order if s not in completed]

    if not remaining:
        stage = SurveyStage.complete.value
    elif not done(quiz_step_id(BASE_QUIZ_ID)):
        stage = SurveyStage.pre_base.value
    elif survey_step_id(SurveyStage.post_base.value) in step_order and not done(survey_step_id(SurveyStage.post_base.value)):
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


def _write_completed_steps(db, doc: dict, completed: list[str], updated_at: datetime) -> dict:
    """Persist a new completed_steps list plus the flags derived from it."""
    doc["completed_steps"] = completed

    update = {"completed_steps": completed, "updated_at": updated_at}
    update.update(derive_legacy_flags(doc))

    db["users"].update_one({"_id": doc["_id"]}, {"$set": update})
    return update


def mark_step_completed(db, user_id: str, step_id: str, completed_at: datetime) -> dict:
    """Record a finished step and refresh the derived legacy flags.

    A step_id outside this user's step_order — an admin test run, or a Phase 13
    quiz-2 id — is a no-op: no write is issued at all.
    """
    if not ObjectId.is_valid(user_id):
        return {}
    doc = db["users"].find_one({"_id": ObjectId(user_id)})
    if not doc:
        return {}

    doc = ensure_user_flow(db, doc)

    completed = list(doc.get("completed_steps") or [])
    if step_id not in (doc.get("step_order") or []) or step_id in completed:
        return {}

    completed.append(step_id)
    return _write_completed_steps(db, doc, completed, completed_at)


def unmark_step_completed(db, user_id: str, step_id: str) -> dict:
    """Reverse of mark_step_completed — used by the admin reset endpoints.

    Like mark_step_completed, a step the user has not completed (including any
    id that isn't part of their flow) is a no-op rather than a redundant write.
    """
    doc = db["users"].find_one({"_id": ObjectId(user_id)})
    if not doc:
        return {}

    doc = ensure_user_flow(db, doc)

    completed = list(doc.get("completed_steps") or [])
    if step_id not in completed:
        return {}

    completed = [s for s in completed if s != step_id]
    return _write_completed_steps(db, doc, completed, datetime.utcnow())
