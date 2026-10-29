"""Request ledger survives cancelled/failed streams; message records remain authoritative."""
import hashlib
import logging
import uuid
import json
from datetime import datetime
from fastapi import HTTPException
from ..core.llm import get_llm_model

logger = logging.getLogger(__name__)
PROMPT_VERSION = "study-chat-1"


def begin_request(db, user, req, conv_id, quiz_id, system_prompts, generation_settings=None):
    if not user.is_admin and db["messages"].find_one({"conversation_id": conv_id, "user_id": {"$ne": user.id}}):
        raise HTTPException(403, "Unauthorized access to conversation")
    attempt = db["quiz_attempts"].find_one({"conversation_id": conv_id, "user_id": user.id})
    if req.request_id and req.question_id and not user.is_admin and not attempt:
        raise HTTPException(403, "Chat is not part of your quiz attempt")
    if attempt and req.question_id and req.question_id not in attempt.get("question_order", []):
        raise HTTPException(422, "Question is not part of this attempt")
    if attempt and req.request_id and attempt["quiz_id"] != quiz_id:
        raise HTTPException(422, "Chat variant does not match this attempt")
    context = {"request_id": req.request_id or str(uuid.uuid4()), "user_id": user.id,
               "conversation_id": conv_id, "question_id": req.question_id, "quiz_id": quiz_id,
               "started_at": datetime.utcnow(), "model_version": get_llm_model(),
               "prompt_version": PROMPT_VERSION,
               "generation_settings": generation_settings or {},
               "prompt_hash": hashlib.sha256(system_prompts.encode()).hexdigest(),
               "attempt_id": str(attempt["_id"]) if attempt else None,
               "trigger": req.trigger, "agents": req.agents, "prompt": req.message,
               "answer_incorrectly": req.answer_incorrectly, "status": "started"}
    update_request(db, context, context)
    return context


def update_request(db, context, fields):
    try:
        db["ai_requests"].update_one(
            {"user_id": context["user_id"], "request_id": context["request_id"]},
            {"$set": fields}, upsert=True)
    except Exception:
        logger.exception("Failed to persist research AI request")


async def track_stream(stream, db, context):
    first_token = False
    main_completed = False
    failed = False
    ended = False
    followup_text = ""
    partial_replies = {}
    try:
        async for chunk in stream:
            if isinstance(chunk, str) and chunk.startswith("data: "):
                try:
                    event = json.loads(chunk[6:])
                    if event.get("type") == "token" and not first_token:
                        first_token = True
                        update_request(db, context, {"first_token_at": datetime.utcnow()})
                    if event.get("type") == "token":
                        agent = event.get("agent", "default")
                        partial_replies[agent] = partial_replies.get(agent, "") + event.get("content", "")
                    if event.get("type") == "done":
                        main_completed = True
                        update_request(db, context, {"response_completed_at": datetime.utcnow()})
                    failed = failed or event.get("type") == "error"
                    if event.get("type") == "followup":
                        followup_text += event.get("token", "")
                except (ValueError, TypeError):
                    pass
            yield chunk
        ended = True
    finally:
        status = "completed" if ended and main_completed and not failed else "failed" if failed else "interrupted"
        update_request(db, context, {"status": status, "stream_ended_at": datetime.utcnow(),
                                     "main_response_completed": main_completed, "followup_text": followup_text,
                                     "user_message_persisted": context.get("user_message_persisted"),
                                     "assistant_message_persisted": context.get("assistant_message_persisted")})
        if not main_completed:
            update_request(db, context, {"partial_visible_replies": partial_replies})
