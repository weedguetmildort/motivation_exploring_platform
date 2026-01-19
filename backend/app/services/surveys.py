# backend/app/services/surveys.py
from datetime import datetime
from typing import List, Optional, Any, Dict
from bson.objectid import ObjectId
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
)

def get_survey_items_collection(db) -> Collection:
    return db["survey_items"]

def get_survey_responses_collection(db) -> Collection:
    return db["survey_responses"]

def ensure_survey_indexes(db) -> None:
    items = get_survey_items_collection(db)
    responses = get_survey_responses_collection(db)

    items.create_index([("stage", 1), ("active", 1), ("order", 1)])
    responses.create_index([("user_id", 1), ("stage", 1)], unique=True)

# ---------- survey items (admin CRUD) ----------

def _item_to_public(doc: dict) -> SurveyItemPublic:
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    return SurveyItemPublic(**d)

def create_survey_item(db, data: SurveyItemCreate) -> SurveyItemPublic:
    ensure_survey_indexes(db)
    col = get_survey_items_collection(db)
    doc = data.model_dump()
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
    update = {k: v for k, v in patch.model_dump().items() if v is not None}
    update["updated_at"] = now

    res = col.update_one({"_id": ObjectId(item_id)}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Survey item not found")

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
    # load items
    items = list_survey_items(db, stage=stage, active_only=True)

    # load or create attempt doc
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
    col = get_survey_responses_collection(db)
    items_col = get_survey_items_collection(db)

    doc = _load_or_create_response_doc(db, user_id, user_email, stage)

    if doc.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Survey already completed")

    # Validate item IDs belong to this stage and are active
    valid_ids = set(str(d["_id"]) for d in items_col.find({"stage": stage, "active": True}, {"_id": 1}))
    for a in req.answers:
        if a.item_id not in valid_ids:
            raise HTTPException(status_code=400, detail=f"Invalid survey item_id: {a.item_id}")

    now = datetime.utcnow()

    # Write each answer (upsert into answers array)
    # Approach: try positional update first; if not present, push a new entry
    for a in req.answers:
        res = col.update_one(
            {"_id": doc["_id"], "answers.item_id": a.item_id},
            {"$set": {"answers.$.value": a.value, "answers.$.answered_at": now, "updated_at": now}},
        )
        if res.matched_count == 0:
            col.update_one(
                {"_id": doc["_id"]},
                {"$push": {"answers": {"item_id": a.item_id, "shown_at": None, "answered_at": now, "value": a.value}},
                 "$set": {"updated_at": now}},
            )

    # mark completed if all required items answered
    updated = col.find_one({"_id": doc["_id"]})

    # compute completion (required only)
    required_ids = set(str(d["_id"]) for d in items_col.find({"stage": stage, "active": True, "required": True}, {"_id": 1}))
    answered_ids = set(x.get("item_id") for x in updated.get("answers", []) if x.get("answered_at"))

    if required_ids.issubset(answered_ids):
        col.update_one(
            {"_id": updated["_id"]},
            {"$set": {"status": "completed", "completed_at": datetime.utcnow(), "updated_at": datetime.utcnow()}},
        )

    return build_survey_state(db, user_id, user_email, stage)
