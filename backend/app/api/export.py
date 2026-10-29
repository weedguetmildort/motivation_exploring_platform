# backend/app/api/export.py
import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..schemas.user import UserPublic
from ..core.study_profiles import study_id_of
from ..api.auth import get_current_user
from ..services.research_analytics import ANALYSIS_VERSION, research_data, research_attempts, variant_summaries

router = APIRouter(prefix="/export", tags=["export"])


def _require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    if not rows:
        buf = io.StringIO()
        buf.write("")
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows([{key: json.dumps(value, default=str) if isinstance(value, (dict, list)) else value
                      for key, value in row.items()} for row in rows])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _fmt(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


# ── Participants ──────────────────────────────────────────────────────────────

@router.get("/participants")
def export_participants(
    request: Request,
    _: UserPublic = Depends(_require_admin),
):
    col = request.app.state.db["users"]
    docs = list(col.find({"is_admin": False}, sort=[("created_at", -1)]))
    rows = []
    for doc in docs:
        rows.append({
            "study_id": doc.get("study_id", "study-1"),
            "id": str(doc["_id"]),
            "email": doc.get("email", ""),
            "first_name": _fmt(doc.get("first_name")),
            "last_name": _fmt(doc.get("last_name")),
            "assigned_var": _fmt(doc.get("assigned_var")),
            "variant_sequence": doc.get("variant_sequence", []),
            "step_order": doc.get("step_order", []),
            "completed_steps": doc.get("completed_steps", []),
            "study_flow_version": doc.get("study_flow_version"),
            "quiz_set_assignment": doc.get("quiz_set_assignment", {}),
            "demographics": doc.get("demographics", {}),
            "survey_stage": _fmt(doc.get("survey_stage")),
            "demographics_completed": _fmt(doc.get("demographics_completed", False)),
            "survey_pre_base_completed": _fmt(doc.get("survey_pre_base_completed", False)),
            "quiz_base_completed": _fmt(doc.get("quiz_base_completed", False)),
            "survey_post_base_completed": _fmt(doc.get("survey_post_base_completed", False)),
            "quiz_variant_completed": _fmt(doc.get("quiz_variant_completed", False)),
            "survey_post_variant_completed": _fmt(doc.get("survey_post_variant_completed", False)),
            "consent": _fmt(doc.get("consent")),
            "consent_given_at": _fmt(doc.get("consent_given_at")),
            "consent_agreed_at": _fmt(doc.get("consent_agreed_at")),
            "consent_declined_at": _fmt(doc.get("consent_declined_at")),
            "consent_viewed_at": _fmt(doc.get("consent_viewed_at")),
            "consent_abandoned_at": _fmt(doc.get("consent_abandoned_at")),
            "last_active_at": _fmt(doc.get("last_active_at")),
            "created_at": _fmt(doc.get("created_at")),
        })
    return _csv_response(rows, "participants.csv")


# ── Quiz Answers ──────────────────────────────────────────────────────────────

@router.get("/quiz-answers")
def export_quiz_answers(
    request: Request,
    _: UserPublic = Depends(_require_admin),
):
    col = request.app.state.db["quiz_attempts"]
    docs = list(col.find({}, sort=[("created_at", 1)]))
    rows = []
    for doc in docs:
        user_email = doc.get("user_email", "")
        quiz_id = doc.get("quiz_id", "")
        status = doc.get("status", "")
        # Which question set this attempt drew from; blank = the whole pool.
        question_set = doc.get("question_set") or ""
        attempt_created = _fmt(doc.get("created_at"))
        for answer in doc.get("answers", []):
            rows.append({
                "study_id": doc.get("study_id", "study-1"),
                "user_email": user_email,
                "participant_id": doc.get("user_id"),
                "attempt_id": str(doc["_id"]),
                "conversation_id": doc.get("conversation_id"),
                "study_flow_version": doc.get("study_flow_version"),
                "variant_position": doc.get("variant_position"),
                "question_version": doc.get("question_snapshots", {}).get(answer.get("question_id"), {}).get("version"),
                "quiz_id": quiz_id,
                "quiz_status": status,
                "question_set": question_set,
                "question_id": answer.get("question_id", ""),
                "choice_id": _fmt(answer.get("choice_id")),
                "marked_correct": _fmt(answer.get("marked_correct")),
                "shown_at": _fmt(answer.get("shown_at")),
                "answered_at": _fmt(answer.get("answered_at")),
                "attempt_created_at": attempt_created,
            })
    return _csv_response(rows, "quiz_answers.csv")


# ── Survey Responses ──────────────────────────────────────────────────────────

@router.get("/survey-responses")
def export_survey_responses(
    request: Request,
    include_archived: bool = False,
    _: UserPublic = Depends(_require_admin),
):
    col = request.app.state.db["survey_responses"]
    docs = list(col.find({}, sort=[("completed_at", 1)]))
    if include_archived:
        docs += list(request.app.state.db["survey_response_archive"].find({}))
    rows = []
    for doc in docs:
        user_id = _fmt(doc.get("user_id"))
        user_email = _fmt(doc.get("user_email"))
        stage = _fmt(doc.get("stage"))
        submitted_at = _fmt(doc.get("completed_at") or doc.get("submitted_at"))
        for answer in doc.get("answers", []):
            rows.append({
                "study_id": doc.get("study_id", "study-1"),
                "user_id": user_id,
                "user_email": user_email,
                "stage": stage,
                "survey_name": doc.get("survey_name", ""),
                "covered_quiz_ids": json.dumps(doc["covered_quiz_ids"]) if "covered_quiz_ids" in doc else "",
                "archived": bool(doc.get("archived_at")),
                "item_id": _fmt(answer.get("item_id")),
                "response_value": _fmt(answer.get("value")),
                "submitted_at": submitted_at,
            })
    return _csv_response(rows, "survey_responses.csv")


# ── Events (copy + link clicks merged) ───────────────────────────────────────

@router.get("/events")
def export_events(
    request: Request,
    _: UserPublic = Depends(_require_admin),
):
    db = request.app.state.db
    copy_docs = list(db["copy_events"].find({}, sort=[("created_at", 1)]))
    link_docs = list(db["link_clicks"].find({}, sort=[("clicked_at", 1)]))

    rows: list[dict] = []
    for doc in copy_docs:
        rows.append({
            "study_id": doc.get("study_id", "study-1"),
            "event_type": "copy",
            "event_id": _fmt(doc.get("_id")), "participant_id": doc.get("user_id"), "conversation_id": doc.get("conversation_id"),
            "user_email": _fmt(doc.get("user_email")),
            "quiz_id": _fmt(doc.get("quiz_id")),
            "question_id": _fmt(doc.get("question_id")),
            "content": doc.get("copied_text", ""),
            "timestamp": _fmt(doc.get("created_at")),
        })
    for doc in link_docs:
        rows.append({
            "study_id": doc.get("study_id", "study-1"),
            "event_type": "link_click",
            "event_id": _fmt(doc.get("_id")), "participant_id": doc.get("user_id"), "conversation_id": doc.get("conversation_id"),
            "user_email": _fmt(doc.get("user_email")),
            "quiz_id": _fmt(doc.get("quiz_id")),
            "question_id": _fmt(doc.get("question_id")),
            "content": doc.get("url", ""),
            "timestamp": _fmt(doc.get("clicked_at")),
        })

    rows.sort(key=lambda r: r["timestamp"])
    return _csv_response(rows, "events.csv")


# ── Chat Messages ─────────────────────────────────────────────────────────────

@router.get("/chat-messages")
def export_chat_messages(
    request: Request,
    _: UserPublic = Depends(_require_admin),
):
    col = request.app.state.db["messages"]
    # AI replies only, as this file has always held. Student prompts are in
    # the research bundle's messages.json.
    docs = list(col.find({"role": "assistant"}, sort=[("created_at", 1)]))
    rows = []
    for doc in docs:
        meta = doc.get("metadata") or {}
        stated = meta.get("stated_choice_id") or {}
        leaked = meta.get("manipulation_leaked") or {}
        rows.append({
            "study_id": doc.get("study_id", "study-1"),
            "user_email": _fmt(doc.get("user_email")),
            "participant_id": doc.get("user_id"), "message_id": _fmt(doc.get("_id")),
            "request_id": doc.get("request_id"), "content": doc.get("content"),
            "model_version": doc.get("model_version") or meta.get("model_version"),
            "prompt_version": doc.get("prompt_version"), "prompt_hash": doc.get("prompt_hash"),
            "conversation_id": _fmt(doc.get("conversation_id")),
            "question_id": _fmt(doc.get("question_id")),
            "trigger": _fmt(doc.get("trigger")),
            "stated_choice_default": _fmt(stated.get("default")),
            "stated_choice_A": _fmt(stated.get("A")),
            "stated_choice_B": _fmt(stated.get("B")),
            "answer_incorrectly": _fmt(meta.get("answer_incorrectly")),
            "manipulation_leaked_default": _fmt(leaked.get("default")),
            "manipulation_leaked_A": _fmt(leaked.get("A")),
            "manipulation_leaked_B": _fmt(leaked.get("B")),
            "created_at": _fmt(doc.get("created_at")),
        })
    return _csv_response(rows, "chat_messages.csv")


@router.get("/research-questions")
def export_research_questions(request: Request, include_tests: bool = False, include_archived: bool = False,
                              _: UserPublic = Depends(_require_admin)):
    return _csv_response(research_data(request.app.state.db, include_tests, include_archived), "research_questions.csv")


@router.get("/research-variants")
def export_research_variants(request: Request, include_tests: bool = False, include_archived: bool = False,
                             _: UserPublic = Depends(_require_admin)):
    return _csv_response(variant_summaries(research_data(request.app.state.db, include_tests, include_archived)), "research_variants.csv")


@router.get("/research-summary")
def get_research_summary(request: Request, _: UserPublic = Depends(_require_admin)):
    return {"analysis_version": ANALYSIS_VERSION, "variants": variant_summaries(research_data(request.app.state.db))}


def _json_value(value):
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _research_bundle_bytes(db, include_tests=False, include_archived=False):
    selected_attempts = research_attempts(db, include_tests, include_archived)
    questions = research_data(db, include_tests, include_archived, attempts=selected_attempts, include_packets=True)
    packets = [row.pop("_conversation_packet") for row in questions]
    variants = variant_summaries(questions)
    participant_ids = {str(u["_id"]) for u in db["users"].find({}) if include_tests or not (u.get("is_admin") or u.get("is_test"))}
    conversations = {attempt.get("conversation_id") for attempt in selected_attempts}
    attempts = {str(attempt["_id"]) for attempt in selected_attempts}
    files = {"questions": questions, "variants": variants, "conversation_packets": packets}
    for collection in ("research_events", "messages", "ai_requests", "quiz_attempts", "quiz_attempt_archive", "survey_responses", "survey_response_archive", "study_flow_repairs", "copy_events", "link_clicks", "reports", "research_annotations"):
        records = []
        for doc in db[collection].find({}):
            if doc.get("user_id") not in participant_ids:
                continue
            if collection in ("quiz_attempts", "quiz_attempt_archive") and str(doc["_id"]) not in attempts:
                continue
            if collection == "survey_response_archive" and not include_archived:
                continue
            if doc.get("conversation_id") and doc["conversation_id"] not in conversations:
                continue
            records.append({key: value for key, value in doc.items() if key not in ("user_email", "reviewer_id")})
            if collection == "research_annotations" and doc.get("reviewer_id"):
                # Stable pseudonym allows inter-rater analysis without account identifiers.
                import hashlib
                records[-1]["reviewer_id"] = hashlib.sha256(str(doc["reviewer_id"]).encode()).hexdigest()
        files[collection] = records
    files["participants"] = [{"participant_id": str(u["_id"]), **{key: u.get(key) for key in (
        "study_id", "study_protocol", "started_at", "study1_finished_at_start", "study_flow_version", "variant_sequence", "assigned_var", "step_order", "completed_steps", "quiz_set_assignment",
        "demographics", "created_at", "last_active_at", "consent", "consent_agreed_at")}}
        for u in db["users"].find({}) if str(u["_id"]) in participant_ids]
    files["survey_items_at_export"] = list(db["survey_items"].find({}))
    manifest = {"analysis_version": ANALYSIS_VERSION, "schema_version": 1,
                "study_id": study_id_of(db, "study-1"),
                "exported_at": datetime.now(timezone.utc).isoformat(), "include_tests": include_tests,
                "include_archived": include_archived, "record_counts": {key: len(value) for key, value in files.items()},
                "definitions": {"accuracy": "Correct submitted answers divided by submitted answers with a stored boolean grade or an immutable attempt answer key. Missing grades are excluded, not counted as incorrect.",
                    "matched_wrong_ai": "Final answer matches an incorrect, detected recommendation with a viewport impression before submission; not evidence of a causal answer change.",
                    "pointer_ms": "Visible, focused time with pointer observed in a named region; not gaze or reading time.",
                    "active_ms": "Visible, focused time within 60 seconds of an interaction; not a measure of cognition.",
                    "intent_labels": "Exploratory keyword labels, requiring human validation.",
                    "conversation_packets": "Timestamped turns at or before submission, frozen question, and displayed suggestions. Viewport-confirmed AI advice is distinguished from persisted replies. Free text may identify a participant.",
                    "missing_values": "Null means unobserved or ineligible; do not replace with zero.",
                    "privacy": "Direct identity fields omitted; free-text responses can still contain identifying information."}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name, records in files.items():
            archive.writestr(f"{name}.json", json.dumps(_json_value(records), indent=2))
    return output.getvalue()


@router.get("/research-bundle")
def export_research_bundle(request: Request, include_tests: bool = False, include_archived: bool = False,
                           _: UserPublic = Depends(_require_admin)):
    from ..services.research_studies import sources
    selected = sources(request)
    if len(selected) == 1:
        content = _research_bundle_bytes(selected[0][1], include_tests, include_archived)
    else:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps({"studies": [sid for sid, _ in selected],
                "definition": "Each nested snapshot preserves study-specific packets and protocol. Shared participant_id identifies the same account across studies. Analyze effects within each study."}))
            for sid, db in selected:
                archive.writestr(f"{sid}_snapshot.zip", _research_bundle_bytes(db, include_tests, include_archived))
        content = output.getvalue()
    return StreamingResponse(iter([content]), media_type="application/zip",
                             headers={"Content-Disposition": 'attachment; filename="research_snapshot.zip"'})
