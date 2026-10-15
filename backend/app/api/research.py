from datetime import datetime, timezone
import json
from typing import Literal
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from .auth import get_current_user
from ..schemas.user import UserPublic
from ..schemas.research import ResearchEventBatch
from ..services.research_dashboard import DEMOGRAPHICS, dashboard, profile, aggregate, comparisons, METRICS
from ..services.research_analytics import research_data, iso, prompt_intents

router = APIRouter(prefix="/research", tags=["research"])


def ensure_research_indexes(db):
    db["research_events"].create_index([("user_id", 1), ("event_id", 1)], unique=True)
    db["research_events"].create_index([("attempt_id", 1), ("question_id", 1)])
    db["ai_requests"].create_index([("user_id", 1), ("request_id", 1)], unique=True)
    db["quiz_attempt_archive"].create_index("conversation_id")


@router.post("/events")
def record_events(batch: ResearchEventBatch, request: Request, user: UserPublic = Depends(get_current_user)):
    db = request.app.state.db
    if user.consent is False:
        raise HTTPException(403, "Study consent is required")
    # Validate the whole batch before writing. Completed and archived attempts
    # remain valid for late deliveries; another participant's never does.
    contexts = {}
    for event in batch.events:
        if event.conversation_id not in contexts:
            query = {"conversation_id": event.conversation_id, "user_id": user.id}
            attempt = db["quiz_attempts"].find_one(query) or db["quiz_attempt_archive"].find_one(query)
            if not attempt:
                raise HTTPException(403, "Unknown research attempt")
            contexts[event.conversation_id] = attempt
        if event.question_id not in contexts[event.conversation_id].get("question_order", []):
            raise HTTPException(422, "Question is not part of this attempt")
    now = datetime.now(timezone.utc)
    accepted = 0
    for event in batch.events:
        attempt = contexts[event.conversation_id]
        doc = event.model_dump(mode="python", exclude_none=True)
        doc.update(user_id=user.id, attempt_id=str(attempt["_id"]), quiz_id=attempt["quiz_id"],
                   study_flow_version=attempt.get("study_flow_version"), schema_version=1, received_at=now)
        result = db["research_events"].update_one(
            {"user_id": user.id, "event_id": event.event_id}, {"$setOnInsert": doc}, upsert=True)
        accepted += int(result.upserted_id is not None)
    return {"accepted": accepted, "duplicates": len(batch.events) - accepted}


def require_research_admin(user: UserPublic = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return user


@router.get("/results")
def research_results(request: Request, _: UserPublic = Depends(require_research_admin),
                     filters: str = Query("{}", max_length=5000), search: str = Query("", max_length=200),
                     age_min: int | None = Query(None, ge=0, le=130), age_max: int | None = Query(None, ge=0, le=130),
                     include_tests: bool = False, include_archived: bool = False,
                     quiz_id: str | None = Query(None, max_length=100), status: Literal["all", "completed", "in_progress"] = "completed",
                     version: int | None = Query(None, ge=1), question_set: Literal["a", "b", "c", "d"] | None = None,
                     variant_position: int | None = Query(None, ge=1), page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    try:
        values = json.loads(filters)
        if not isinstance(values, dict) or any(k not in DEMOGRAPHICS or not isinstance(v, str) or len(v) > 500 for k, v in values.items()):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, "Invalid demographic filters")
    if age_min is not None and age_max is not None and age_min > age_max:
        raise HTTPException(422, "Minimum age cannot exceed maximum age")
    return dashboard(request.app.state.db, filters=values, search=search, age_min=age_min, age_max=age_max,
                     include_tests=include_tests, include_archived=include_archived, quiz_id=quiz_id, status=status,
                     version=version, question_set=question_set, variant_position=variant_position, page=page, page_size=page_size)


def _participant(db, participant_id, include_tests):
    if not ObjectId.is_valid(participant_id):
        raise HTTPException(404, "Participant not found")
    user = db["users"].find_one({"_id": ObjectId(participant_id)})
    if not user or (not include_tests and (user.get("is_admin") or user.get("is_test"))):
        raise HTTPException(404, "Participant not found")
    return user


@router.get("/participants/{participant_id}")
def research_participant(participant_id: str, request: Request, include_tests: bool = False, include_archived: bool = False,
                         _: UserPublic = Depends(require_research_admin)):
    db = request.app.state.db
    user = _participant(db, participant_id, include_tests)
    rows = research_data(db, include_tests, include_archived, participant_ids={participant_id})
    rows.sort(key=lambda r: (r["variant_position"] is None, r["variant_position"] or 0, r["quiz_id"], r["attempt_id"], r["question_position"]))
    return {"participant": profile(user), "metric_definitions": METRICS, "overall": aggregate(rows),
            "variants": comparisons(rows), "questions": rows}


@router.get("/participants/{participant_id}/questions/{attempt_id}/{question_id}")
def research_question(participant_id: str, attempt_id: str, question_id: str, request: Request,
                      include_tests: bool = False, include_archived: bool = False,
                      event_page: int = Query(1, ge=1), event_page_size: int = Query(100, ge=1, le=500),
                      _: UserPublic = Depends(require_research_admin)):
    db = request.app.state.db
    _participant(db, participant_id, include_tests)
    if not ObjectId.is_valid(attempt_id):
        raise HTTPException(404, "Attempt not found")
    query = {"_id": ObjectId(attempt_id), "user_id": participant_id}
    attempt = db["quiz_attempts"].find_one(query)
    if not attempt and include_archived:
        attempt = db["quiz_attempt_archive"].find_one(query)
    if not attempt or question_id not in attempt.get("question_order", []):
        raise HTTPException(404, "Question not found for this participant")
    query = {"user_id": participant_id, "conversation_id": attempt["conversation_id"], "question_id": question_id}
    messages = [{"id": str(m["_id"]), "role": m.get("role"), "content": m.get("content"),
                 "created_at": iso(m.get("created_at")), "request_id": m.get("request_id"), "trigger": m.get("trigger"),
                 "stated_choice_id": (m.get("metadata") or {}).get("stated_choice_id"),
                 "model_version": m.get("model_version"),
                 "intent_labels_heuristic": prompt_intents(m["content"]) if m.get("role") == "user" and isinstance(m.get("content"), str) and m.get("trigger") != "auto_question" else []}
                for m in db["messages"].find(query).sort("created_at", 1)]
    event_count = db["research_events"].count_documents(query)
    events = [{"event_id": e.get("event_id"), "event_type": e.get("event_type"), "page_id": e.get("page_id"),
               "sequence": e.get("sequence"), "elapsed_ms": e.get("elapsed_ms"), "occurred_at": iso(e.get("occurred_at")),
               "data": e.get("data", {})} for e in db["research_events"].find(query).sort([("occurred_at", 1), ("sequence", 1), ("_id", 1)]).skip((event_page - 1) * event_page_size).limit(event_page_size)]
    requests = [{"request_id": r.get("request_id"), "prompt": r.get("prompt"), "trigger": r.get("trigger"),
                 "status": r.get("status"), "started_at": iso(r.get("started_at")),
                 "first_token_at": iso(r.get("first_token_at")), "response_completed_at": iso(r.get("response_completed_at")),
                 "partial_visible_replies": r.get("partial_visible_replies"), "followup_text": r.get("followup_text")}
                for r in db["ai_requests"].find(query).sort("started_at", 1)]
    return {"snapshot": attempt.get("question_snapshots", {}).get(question_id), "messages": messages, "events": events, "requests": requests,
            "events_total": event_count, "events_pages": (event_count + event_page_size - 1) // event_page_size}
