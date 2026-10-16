from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from .auth import get_current_user
from ..schemas.user import UserPublic
from ..services.studies import (STUDY_IDS, StudyDatabase, raw_database, enrollment_status,
                               check_access, approve_study2)

router = APIRouter(prefix="/studies", tags=["studies"])


def admin(user: UserPublic = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return user


@router.get("/catalog")
def catalog(request: Request, user: UserPublic = Depends(get_current_user)):
    raw = raw_database(request.app.state.db)
    doc = raw["users"].find_one({"_id": ObjectId(user.id)})
    return {"studies": [enrollment_status(raw, doc, sid) for sid in STUDY_IDS]}


@router.post("/start")
def start(request: Request, user: UserPublic = Depends(get_current_user)):
    # Mounted after /studies/{id} routing. No approval is granted here.
    db = request.app.state.db
    sid = getattr(db, "study_id", "study-1")
    raw = raw_database(db)
    doc = raw["users"].find_one({"_id": ObjectId(user.id)})
    check_access(raw, doc, sid)
    from ..services.study_flow import ensure_user_flow
    scoped = StudyDatabase(raw, sid)
    progress = ensure_user_flow(scoped, scoped["users"].find_one({"_id": doc["_id"]}))
    if not progress.get("started_at"):
        now = datetime.now(timezone.utc)
        first = enrollment_status(raw, doc, "study-1")
        scoped["users"].update_one({"_id": doc["_id"], "started_at": None}, {"$set": {
            "started_at": now, "study1_finished_at_start": first["finished"],
        }})
    return enrollment_status(raw, doc, sid)


class AccessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool
    interview_at: datetime | None = None
    notes: str = Field("", max_length=4000)


@router.get("/participants")
def participants(request: Request, search: str = Query("", max_length=200),
                 page: int = Query(1, ge=1), _: UserPublic = Depends(admin)):
    raw = raw_database(request.app.state.db)
    import re
    query = {"is_admin": {"$ne": True}}
    if search.strip():
        pattern = {"$regex": re.escape(search.strip()), "$options": "i"}
        query["$or"] = [{field: pattern} for field in ("email", "first_name", "last_name")]
        # A pasted full name spans two stored fields. Match each name token
        # independently while retaining literal email / account ID searches.
        tokens = search.strip().split()
        if len(tokens) > 1:
            query["$or"].append({"$and": [{"$or": [
                {field: {"$regex": re.escape(token), "$options": "i"}} for field in ("first_name", "last_name")
            ]} for token in tokens]})
        if ObjectId.is_valid(search.strip()):
            query["$or"].append({"_id": ObjectId(search.strip())})
    users = list(raw["users"].find(query).sort([("created_at", -1), ("_id", 1)]).skip((page - 1) * 25).limit(25))
    result = []
    for user in users:
        enrollment = raw["study_enrollments"].find_one({"_id": user["_id"]}) or {}
        result.append({"id": str(user["_id"]), "email": user["email"],
            "name": " ".join(user.get(k) or "" for k in ("first_name", "last_name")).strip(),
            **enrollment_status(raw, user, "study-2"),
            "notes": enrollment.get("interviewer_notes", ""),
            "access_history": [{**h, "at": h["at"].isoformat()} for h in enrollment.get("access_history", [])]})
    return {"participants": result, "page": page, "total": raw["users"].count_documents(query)}


@router.patch("/participants/{user_id}/study-2-access")
def access(user_id: str, data: AccessUpdate, request: Request, user: UserPublic = Depends(admin)):
    return approve_study2(raw_database(request.app.state.db), user_id, user.id, data.approved,
                          data.interview_at, data.notes)
