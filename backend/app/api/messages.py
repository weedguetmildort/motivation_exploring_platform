# backend/app/api/messages.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query

from ..schemas.message import MessageSummary
from ..schemas.user import UserPublic
from ..api.auth import get_current_user

router = APIRouter(prefix="/messages", tags=["messages"])


def _require_admin(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _to_summary(doc: dict) -> MessageSummary:
    meta = doc.get("metadata") or {}
    return MessageSummary(
        id=str(doc["_id"]),
        conversation_id=doc.get("conversation_id", ""),
        user_id=doc.get("user_id"),
        user_email=doc.get("user_email"),
        question_id=doc.get("question_id"),
        trigger=doc.get("trigger"),
        stated_choice_id=meta.get("stated_choice_id"),
        answer_incorrectly=meta.get("answer_incorrectly"),
        manipulation_leaked=meta.get("manipulation_leaked"),
        created_at=doc["created_at"],
    )


@router.get("", response_model=list[MessageSummary])
def list_messages(
    request: Request,
    _: UserPublic = Depends(_require_admin),
    question_id: Optional[str] = Query(default=None),
    has_choice: Optional[bool] = Query(default=None),
    leaked_only: Optional[bool] = Query(
        default=None,
        description="If true, only return replies flagged as having leaked the answer_incorrectly instruction.",
    ),
):
    db = request.app.state.db
    col = db["messages"]

    query: dict = {"role": "assistant"}
    if question_id:
        query["question_id"] = question_id
    if has_choice:
        query["metadata.stated_choice_id"] = {"$exists": True, "$ne": None}
    if leaked_only:
        query["$or"] = [
            {"metadata.manipulation_leaked.default": True},
            {"metadata.manipulation_leaked.A": True},
            {"metadata.manipulation_leaked.B": True},
        ]

    docs = list(col.find(query, sort=[("created_at", -1)], limit=2000))
    return [_to_summary(doc) for doc in docs]
