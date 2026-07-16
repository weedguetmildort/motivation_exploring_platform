# backend/app/api/export.py
import csv
import io
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..schemas.user import UserPublic
from ..api.auth import get_current_user

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
    writer.writerows(rows)
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
            "id": str(doc["_id"]),
            "email": doc.get("email", ""),
            "first_name": _fmt(doc.get("first_name")),
            "last_name": _fmt(doc.get("last_name")),
            "assigned_var": _fmt(doc.get("assigned_var")),
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
        attempt_created = _fmt(doc.get("created_at"))
        for answer in doc.get("answers", []):
            rows.append({
                "user_email": user_email,
                "quiz_id": quiz_id,
                "quiz_status": status,
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
    _: UserPublic = Depends(_require_admin),
):
    col = request.app.state.db["survey_responses"]
    docs = list(col.find({}, sort=[("submitted_at", 1)]))
    rows = []
    for doc in docs:
        user_id = _fmt(doc.get("user_id"))
        user_email = _fmt(doc.get("user_email"))
        stage = _fmt(doc.get("stage"))
        submitted_at = _fmt(doc.get("submitted_at"))
        for answer in doc.get("answers", []):
            rows.append({
                "user_id": user_id,
                "user_email": user_email,
                "stage": stage,
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
            "event_type": "copy",
            "user_email": _fmt(doc.get("user_email")),
            "quiz_id": _fmt(doc.get("quiz_id")),
            "question_id": _fmt(doc.get("question_id")),
            "content": doc.get("copied_text", ""),
            "timestamp": _fmt(doc.get("created_at")),
        })
    for doc in link_docs:
        rows.append({
            "event_type": "link_click",
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
    docs = list(col.find({"role": "assistant"}, sort=[("created_at", 1)]))
    rows = []
    for doc in docs:
        meta = doc.get("metadata") or {}
        stated = meta.get("stated_choice_id") or {}
        rows.append({
            "user_email": _fmt(doc.get("user_email")),
            "conversation_id": _fmt(doc.get("conversation_id")),
            "question_id": _fmt(doc.get("question_id")),
            "trigger": _fmt(doc.get("trigger")),
            "stated_choice_default": _fmt(stated.get("default")),
            "stated_choice_A": _fmt(stated.get("A")),
            "stated_choice_B": _fmt(stated.get("B")),
            "answer_incorrectly": _fmt(meta.get("answer_incorrectly")),
            "created_at": _fmt(doc.get("created_at")),
        })
    return _csv_response(rows, "chat_messages.csv")
