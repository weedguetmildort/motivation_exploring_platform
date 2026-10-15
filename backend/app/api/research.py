from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from .auth import get_current_user
from ..schemas.user import UserPublic
from ..schemas.research import ResearchEventBatch

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
