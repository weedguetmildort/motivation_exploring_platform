from datetime import datetime, timezone
import json
from typing import Literal
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from .auth import get_current_user
from ..schemas.user import UserPublic
from ..schemas.research import ResearchEventBatch
from ..services.research_dashboard import DEMOGRAPHICS, dashboard, profile, aggregate, comparisons, METRICS
from ..services.research_analytics import research_data, research_attempts, iso, prompt_intents
from ..services.quiz_grading import answer_correctness
from ..services import research_coding as coding
from ..schemas.research_coding import HumanCodingRequest, ModelCodingRequest, ConversationCoding
from ..services.research_statistics import paired_comparisons, survey_associations

from ..services.research_studies import sources, detail_database, combined_dashboard

router = APIRouter(prefix="/research", tags=["research"])


def ensure_research_indexes(db):
    db["research_events"].create_index([("user_id", 1), ("event_id", 1)], unique=True)
    db["research_events"].create_index([("attempt_id", 1), ("question_id", 1)])
    db["ai_requests"].create_index([("user_id", 1), ("request_id", 1)], unique=True)
    db["quiz_attempt_archive"].create_index("conversation_id")
    db["research_annotations"].create_index([("user_id", 1), ("attempt_id", 1), ("question_id", 1), ("packet_hash", 1)])


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


def _filters(filters, age_min, age_max):
    try:
        values = json.loads(filters)
        if not isinstance(values, dict) or any(k not in DEMOGRAPHICS or not isinstance(v, str) or len(v) > 500 for k, v in values.items()):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, "Invalid demographic filters")
    if age_min is not None and age_max is not None and age_min > age_max:
        raise HTTPException(422, "Minimum age cannot exceed maximum age")
    return values


@router.get("/results")
def research_results(request: Request, _: UserPublic = Depends(require_research_admin),
                     filters: str = Query("{}", max_length=5000), search: str = Query("", max_length=200),
                     age_min: int | None = Query(None, ge=0, le=130), age_max: int | None = Query(None, ge=0, le=130),
                     include_tests: bool = False, include_archived: bool = False,
                     quiz_id: str | None = Query(None, max_length=100), status: Literal["all", "completed", "in_progress"] = "completed",
                     version: int | None = Query(None, ge=1), question_set: Literal["a", "b", "c", "d"] | None = None,
                     variant_position: int | None = Query(None, ge=1), page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    values = _filters(filters, age_min, age_max)
    options = dict(filters=values, search=search, age_min=age_min, age_max=age_max,
        include_tests=include_tests, include_archived=include_archived, quiz_id=quiz_id, status=status,
        version=version, question_set=question_set, variant_position=variant_position, page=page, page_size=page_size)
    selected = sources(request)
    if len(selected) > 1:
        return combined_dashboard(selected, **options)
    result = dashboard(selected[0][1], **options)
    result["study_id"] = selected[0][0]
    return result


@router.get("/statistics")
def research_statistics(request: Request, _: UserPublic = Depends(require_research_admin),
                        filters: str = Query("{}", max_length=5000), search: str = Query("", max_length=200),
                        age_min: int | None = Query(None, ge=0, le=130), age_max: int | None = Query(None, ge=0, le=130),
                        include_tests: bool = False, include_archived: bool = False,
                        quiz_id: str | None = Query(None, max_length=100), status: Literal["all", "completed", "in_progress"] = "completed",
                        version: int | None = Query(None, ge=1), question_set: Literal["a", "b", "c", "d"] | None = None,
                        variant_position: int | None = Query(None, ge=1)):
    from ..services.research_dashboard import filter_users, filter_rows
    selected_sources = sources(request)
    reports = []
    for sid, db in selected_sources:
        users = [u for u in db["users"].find({}) if include_tests or not (u.get("is_admin") or u.get("is_test"))]
        selected = filter_users(users, _filters(filters, age_min, age_max), search, age_min, age_max)
        ids = {str(u["_id"]) for u in selected}
        rows = filter_rows(research_data(db, include_tests, include_archived, participant_ids=ids), quiz_id, status, version, question_set, variant_position)
        report = {"paired": paired_comparisons(rows), "surveys": survey_associations(rows,
            [{"participant_id": str(u["_id"]), "assigned_var": u.get("assigned_var")} for u in selected],
            list(db["survey_responses"].find({"user_id": {"$in": list(ids)}})) +
            (list(db["survey_response_archive"].find({"user_id": {"$in": list(ids)}})) if include_archived else []), list(db["survey_items"].find({})))}
        for row in report["paired"]["comparisons"] + report["surveys"]["associations"]:
            row["study_id"] = sid
        reports.append(report)
    if len(reports) == 1:
        return reports[0]
    return {"paired": {"comparisons": [r for report in reports for r in report["paired"]["comparisons"]],
                       "limitations": list(dict.fromkeys(text for report in reports for text in report["paired"]["limitations"])) + ["Effects are estimated separately within each study; different protocols are not pooled."]},
            "surveys": {"associations": [r for report in reports for r in report["surveys"]["associations"]],
                        "limitations": reports[0]["surveys"]["limitations"]}}



def _participant(db, participant_id, include_tests):
    if not ObjectId.is_valid(participant_id):
        raise HTTPException(404, "Participant not found")
    user = db["users"].find_one({"_id": ObjectId(participant_id)})
    if not user or (not include_tests and (user.get("is_admin") or user.get("is_test"))):
        raise HTTPException(404, "Participant not found")
    return user


@router.get("/coding/validation")
def coding_validation(request: Request, include_tests: bool = False, include_archived: bool = False,
                      _: UserPublic = Depends(require_research_admin)):
    records = []
    for sid, db in sources(request):
        rows = research_data(db, include_tests, include_archived)
        current = {(r["participant_id"], r["attempt_id"], r["question_id"], r["conversation_packet_hash"]) for r in rows}
        records.extend(a for a in db["research_annotations"].find({}) if
            (a["user_id"], a["attempt_id"], a["question_id"], a["packet_hash"]) in current)
    return coding.validation_report(records)


def _coding_packet(request, participant_id, attempt_id, question_id, include_tests, include_archived):
    participant_id, db = detail_database(request, participant_id)
    _participant(db, participant_id, include_tests)
    return coding.load_packet(db, participant_id, attempt_id, question_id, include_tests, include_archived)


@router.get("/participants/{participant_id}/questions/{attempt_id}/{question_id}/coding")
def question_coding(participant_id: str, attempt_id: str, question_id: str, request: Request,
                    include_tests: bool = False, include_archived: bool = False,
                    _: UserPublic = Depends(require_research_admin)):
    packet = _coding_packet(request, participant_id, attempt_id, question_id, include_tests, include_archived)
    return {"packet": packet, "rubric": coding.rubric_public(), "rubric_version": coding.RUBRIC_VERSION,
            "annotations": coding.current_annotations(detail_database(request, participant_id)[1], packet), "evaluator": coding.evaluator_status(),
            "partition": coding.validation_partition(packet["participant_id"])}


@router.post("/participants/{participant_id}/questions/{attempt_id}/{question_id}/coding/review")
def review_question(participant_id: str, attempt_id: str, question_id: str, data: HumanCodingRequest, request: Request,
                    include_tests: bool = False, include_archived: bool = False,
                    user: UserPublic = Depends(require_research_admin)):
    packet = _coding_packet(request, participant_id, attempt_id, question_id, include_tests, include_archived)
    if packet["packet_hash"] != data.packet_hash:
        raise HTTPException(409, "Conversation changed; reload the packet before reviewing")
    if not packet["answer"].get("answered_at"):
        raise HTTPException(409, "Only submitted questions can be reviewed")
    return coding.save_annotation(detail_database(request, participant_id)[1], packet, ConversationCoding(
        labels=data.labels, evidence=data.evidence, notes=data.notes), source="human", reviewer_id=user.id,
        independent_review=data.independent_review)


@router.post("/participants/{participant_id}/questions/{attempt_id}/{question_id}/coding/evaluate")
async def evaluate_question(participant_id: str, attempt_id: str, question_id: str, data: ModelCodingRequest, request: Request,
                            include_tests: bool = False, include_archived: bool = False,
                            _: UserPublic = Depends(require_research_admin)):
    packet = _coding_packet(request, participant_id, attempt_id, question_id, include_tests, include_archived)
    if packet["packet_hash"] != data.packet_hash:
        raise HTTPException(409, "Conversation changed; reload the packet before evaluating")
    return await coding.evaluate_packet(detail_database(request, participant_id)[1], packet)


@router.get("/participants/{participant_id}")
def research_participant(participant_id: str, request: Request, include_tests: bool = False, include_archived: bool = False,
                         _: UserPublic = Depends(require_research_admin)):
    participant_id, db = detail_database(request, participant_id)
    user = _participant(db, participant_id, include_tests)
    attempts = research_attempts(db, include_tests, include_archived, participant_ids={participant_id}, users={participant_id: user})
    rows = research_data(db, include_tests, include_archived, participant_ids={participant_id}, attempts=attempts)
    rows.sort(key=lambda r: (r["variant_position"] is None, r["variant_position"] or 0, r["quiz_id"], r["attempt_id"], r["question_position"]))
    return {"participant": profile(user), "metric_definitions": METRICS, "overall": aggregate(rows, attempts),
            "variants": comparisons(rows, attempts), "questions": rows}


@router.get("/participants/{participant_id}/questions/{attempt_id}/{question_id}")
def research_question(participant_id: str, attempt_id: str, question_id: str, request: Request,
                      include_tests: bool = False, include_archived: bool = False,
                      event_page: int = Query(1, ge=1), event_page_size: int = Query(100, ge=1, le=500),
                      _: UserPublic = Depends(require_research_admin)):
    participant_id, db = detail_database(request, participant_id)
    _participant(db, participant_id, include_tests)
    if not ObjectId.is_valid(attempt_id):
        raise HTTPException(404, "Attempt not found")
    query = {"_id": ObjectId(attempt_id), "user_id": participant_id}
    attempt = db["quiz_attempts"].find_one(query)
    if not attempt and include_archived:
        attempt = db["quiz_attempt_archive"].find_one(query)
    if not attempt or question_id not in attempt.get("question_order", []):
        raise HTTPException(404, "Question not found for this participant")
    query = {"user_id": participant_id, "question_id": question_id}
    if attempt.get("conversation_id"):
        query["conversation_id"] = attempt["conversation_id"]
    else:
        # Legacy attempts can lack conversation IDs. Do not join unrelated
        # conversations just because they used the same question.
        query["attempt_id"] = str(attempt["_id"])
    snapshot = attempt.get("question_snapshots", {}).get(question_id) or None
    answer = next((a for a in attempt.get("answers", []) if a.get("question_id") == question_id and a.get("answered_at")), {})
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
    copies = [{"id": str(c["_id"]), "text": c.get("copied_text"), "created_at": iso(c.get("created_at"))}
              for c in db["copy_events"].find(query).sort("created_at", 1)]
    return {"snapshot": snapshot, "snapshot_source": "attempt" if snapshot else "unavailable",
            "answer": {"choice_id": answer.get("choice_id"), "correct_choice_id": (snapshot or {}).get("correct_choice_id"),
                       "correct": answer_correctness(answer, snapshot), "answered_at": iso(answer.get("answered_at"))},
            "messages": messages, "events": events, "requests": requests,
            "copies": copies,
            "events_total": event_count, "events_pages": (event_count + event_page_size - 1) // event_page_size}
