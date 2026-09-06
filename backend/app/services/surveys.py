# backend/app/services/surveys.py
import random
from datetime import datetime
from typing import List, Optional, Any, Dict
from bson.objectid import ObjectId
from pymongo import ReturnDocument
from pymongo.collection import Collection
from fastapi import HTTPException

from ..schemas.survey import (
    SurveyItemCreate,
    SurveyItemUpdate,
    SurveyItemPublic,
    SurveySubmitRequest,
    SurveyStateResponse,
    SurveyAttemptPublic,
    SurveyAnswerPublic,
    SurveyScale,
)

from . import study_flow

def get_survey_items_collection(db) -> Collection:
    return db["survey_items"]

def get_survey_responses_collection(db) -> Collection:
    return db["survey_responses"]

def ensure_survey_indexes(db) -> None:
    items = get_survey_items_collection(db)
    responses = get_survey_responses_collection(db)

    items.create_index([("stage", 1), ("active", 1), ("order", 1)])
    responses.create_index([("user_id", 1), ("stage", 1)], unique=True)

# --------------- helper functions ---------------

def get_users_collection(db) -> Collection:
    return db["users"]

def _validate_stage(stage: str) -> str:
    """Accept any stage the study-flow registry knows about.

    Stages used to be limited to the four SurveyStage enum members. The flow now
    schedules one interstitial survey per variant (post_followup, post_links,
    post_double, ...), each of which needs its OWN response stage because
    survey_responses is uniquely indexed on (user_id, stage) — sharing
    "post_base" would make the second survey read back the first's completed
    document and skip straight past it.
    """
    if not study_flow.is_known_survey_stage(stage):
        raise HTTPException(status_code=400, detail=f"Invalid survey stage: {stage}")
    return stage

def _question_stage_for_stage(stage: str) -> str:
    """Which stage's *questions* a response stage displays.

    Every post-variant survey reuses the post_base question set, so admins keep
    editing one list in the Surveys Panel rather than one per variant.
    """
    return study_flow.survey_question_stage(stage) or stage


def _seeded_shuffle(items: List, seed_str: str) -> List:
    """Return a copy of ``items`` shuffled deterministically from ``seed_str``.

    Each participant sees a stable, randomized question order: ``random.Random``
    seeds strings via SHA-512, so the same seed always yields the same order
    across processes (independent of PYTHONHASHSEED). Because it is a pure
    function of the seed, the presented order is reproducible offline from the
    seed alone if order-effect analysis is ever needed — nothing is stored.
    """
    shuffled = list(items)
    random.Random(seed_str).shuffle(shuffled)
    return shuffled

# ---------- survey items (admin CRUD) ----------

def _item_to_public(doc: dict) -> SurveyItemPublic:
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    return SurveyItemPublic(**d)

def _normalize_item_doc(doc: dict) -> dict:
    """
    Enforce invariants based on item.type.
    - likert => must have scale, options=None
    - single_select => must have >=2 options, scale=None
    """
    t = doc.get("type", "likert")

    if t == "likert":
        if not doc.get("scale"):
            doc["scale"] = SurveyScale(min=1, max=5, anchors=["Strongly disagree", "Strongly agree"]).model_dump()  # [ADD]
        doc["options"] = None  # [ADD]

    elif t == "single_select":
        opts = doc.get("options") or []
        # remove empty labels defensively
        normalized = []
        for o in opts:
            label = (o.get("label") or "").strip()
            if not label:
                continue
            normalized.append({"id": o.get("id"), "label": label})

        if len(normalized) < 2:
            raise HTTPException(status_code=400, detail="single_select requires at least 2 options")  # [ADD]

        doc["options"] = normalized  # [ADD]
        doc["scale"] = None          # [ADD]

    else:
        raise HTTPException(status_code=400, detail=f"Unknown survey item type: {t}")  # [ADD]

    return doc  # [ADD]

def create_survey_item(db, data: SurveyItemCreate) -> SurveyItemPublic:
    ensure_survey_indexes(db)
    col = get_survey_items_collection(db)
    doc = _normalize_item_doc(data.model_dump())
    now = datetime.utcnow()
    doc["created_at"] = now
    doc["updated_at"] = now
    res = col.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _item_to_public(doc)

def list_survey_items(db, stage: Optional[str] = None, active_only: bool = False) -> List[SurveyItemPublic]:
    ensure_survey_indexes(db)
    col = get_survey_items_collection(db)
    query = {}
    if stage:
        query["stage"] = stage
    if active_only:
        query["active"] = True

    docs = list(col.find(query).sort("order", 1))
    return [_item_to_public(d) for d in docs]

def update_survey_item(db, item_id: str, patch: SurveyItemUpdate) -> SurveyItemPublic:
    col = get_survey_items_collection(db)
    now = datetime.utcnow()

    existing = col.find_one({"_id": ObjectId(item_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="Survey item not found")  # [UPDATE]

    patch_data = {k: v for k, v in patch.model_dump().items() if v is not None}  # [UPDATE]

    # Merge patch into existing doc
    merged = dict(existing)  # [ADD]
    merged.update(patch_data)  # [ADD]
    merged["updated_at"] = now  # [UPDATE]

    # Normalize & validate based on final type
    merged = _normalize_item_doc(merged)  # [ADD]

    # Write back only the fields we store (avoid overwriting _id)
    merged_to_set = dict(merged)  # [ADD]
    merged_to_set.pop("_id", None)  # [ADD]

    col.update_one({"_id": ObjectId(item_id)}, {"$set": merged_to_set})  # [UPDATE]

    doc = col.find_one({"_id": ObjectId(item_id)})
    return _item_to_public(doc)


def delete_survey_item(db, item_id: str) -> None:
    col = get_survey_items_collection(db)
    res = col.delete_one({"_id": ObjectId(item_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Survey item not found")

# ---------- user survey state + submit ----------

def _load_or_create_response_doc(db, user_id: str, user_email: str, stage: str) -> dict:
    ensure_survey_indexes(db)
    col = get_survey_responses_collection(db)

    doc = col.find_one({"user_id": user_id, "stage": stage})
    if doc:
        return doc

    now = datetime.utcnow()
    doc = {
        "user_id": user_id,
        "user_email": user_email,
        "stage": stage,
        "status": "in_progress",
        "answers": [],
        "started_at": now,
        "completed_at": None,
        "updated_at": now,
    }
    res = col.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc

def build_survey_state(db, user_id: str, user_email: str, stage: str) -> SurveyStateResponse:
    stage = _validate_stage(stage)
    question_stage = _question_stage_for_stage(stage)

    # load items from question source stage
    items = list_survey_items(db, stage=question_stage, active_only=True)

    # Randomize question order per participant to control for order/anchoring
    # effects. Seed on the actual response `stage` (not question_stage) so that
    # post_base and post_variant — which reuse the same question set — get
    # different orders for the same participant. Stable across refreshes.
    items = _seeded_shuffle(items, f"{user_id}:{stage}")

    # load or create attempt doc from actual response stage
    doc = _load_or_create_response_doc(db, user_id, user_email, stage)

    answered_count = sum(1 for a in doc.get("answers", []) if a.get("answered_at"))
    total_items = len(items)

    attempt = SurveyAttemptPublic(
        stage=stage,
        status=doc.get("status", "in_progress"),
        answered_count=answered_count,
        total_items=total_items,
    )

    answers_pub = []
    for a in doc.get("answers", []):
        answers_pub.append(
            SurveyAnswerPublic(
                item_id=a.get("item_id"),
                value=a.get("value"),
                shown_at=a.get("shown_at").isoformat() if a.get("shown_at") else None,
                answered_at=a.get("answered_at").isoformat() if a.get("answered_at") else None,
            )
        )

    return SurveyStateResponse(attempt=attempt, items=items, answers=answers_pub)

def record_item_shown(db, user_id: str, stage: str, item_id: str) -> None:
    col = get_survey_responses_collection(db)
    now = datetime.utcnow()

    # Only add shown_at if item entry doesn't exist yet
    col.update_one(
        {"user_id": user_id, "stage": stage, "answers.item_id": {"$ne": item_id}},
        {"$push": {"answers": {"item_id": item_id, "shown_at": now, "answered_at": None, "value": None}},
         "$set": {"updated_at": now}},
    )

def submit_survey(db, user_id: str, user_email: str, stage: str, req: SurveySubmitRequest) -> SurveyStateResponse:
    # Validate before touching the DB — an unknown stage must not create a
    # response document for itself.
    stage = _validate_stage(stage)

    col = get_survey_responses_collection(db)
    items_col = get_survey_items_collection(db)

    doc = _load_or_create_response_doc(db, user_id, user_email, stage)

    if doc.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Survey already completed")

    question_stage = _question_stage_for_stage(stage)

    # Validate item IDs against the question stage, not necessarily the response stage
    valid_ids = set(
        str(d["_id"])
        for d in items_col.find({"stage": question_stage, "active": True}, {"_id": 1})
    )
    for a in req.answers:
        if a.item_id not in valid_ids:
            raise HTTPException(status_code=400, detail=f"Invalid survey item_id: {a.item_id}")

    now = datetime.utcnow()

    for a in req.answers:
        res = col.update_one(
            {"_id": doc["_id"], "answers.item_id": a.item_id},
            {"$set": {"answers.$.value": a.value, "answers.$.answered_at": now, "updated_at": now}},
        )
        if res.matched_count == 0:
            col.update_one(
                {"_id": doc["_id"]},
                {
                    "$push": {
                        "answers": {
                            "item_id": a.item_id,
                            "shown_at": None,
                            "answered_at": now,
                            "value": a.value,
                        }
                    },
                    "$set": {"updated_at": now},
                },
            )

    updated = col.find_one({"_id": doc["_id"]})

    # Compute completion using the question stage's required items
    required_ids = set(
        str(d["_id"])
        for d in items_col.find(
            {"stage": question_stage, "active": True, "required": True},
            {"_id": 1},
        )
    )
    answered_ids = set(
        x.get("item_id") for x in updated.get("answers", []) if x.get("answered_at")
    )

    if required_ids.issubset(answered_ids):
        completed_at = datetime.utcnow()

        col.update_one(
            {"_id": updated["_id"]},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": completed_at,
                    "updated_at": completed_at,
                }
            },
        )

        users = get_users_collection(db)
        answers_map: Dict[str, Any] = {a.item_id: a.value for a in req.answers}

        # Denormalised copy of the answers on the user doc, one key per stage.
        # Keeps the existing pre_quiz_survey / post_base_survey / post_variant_survey
        # naming convention and extends it to the per-variant stages.
        set_doc: Dict[str, Any] = {
            "updated_at": completed_at,
            f"{stage}_survey": answers_map,
            f"{stage}_survey_completed_at": completed_at,
        }

        user_result = users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": set_doc},
        )

        if user_result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")

        # Advance the flow. This also refreshes the derived legacy booleans
        # (survey_pre_base_completed, survey_stage, ...) that used to be written
        # by hand here via _completion_flag_field.
        study_flow.mark_step_completed(
            db, user_id, study_flow.survey_step_id(stage), completed_at
        )

    return build_survey_state(db, user_id, user_email, stage)
