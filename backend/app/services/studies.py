"""One identity, independent study enrollments, one MongoDB database.

Study 1 retains legacy collection names and progress, avoiding destructive
migration. Study 2 stores progress in study_enrollments and results in study2__
collections in the SAME database. Question definitions are shared; each
attempt retains its immutable question snapshot. Survey definitions are copied
once, then edited independently per study. Collection.database is scoped
as well, so service helpers cannot accidentally use another study's counters.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from bson import ObjectId
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

STUDY_IDS = ("study-1", "study-2")
GLOBAL_FIELDS = {"email", "password_hash", "first_name", "last_name", "is_admin", "is_test",
                 "demographics", "demographics_completed", "created_at", "last_active_at"}
SHARED_COLLECTIONS = {"questions", "knowledge_links", "allowlist"}
PROFILES = {
    "study-1": {"mode": "single_variant", "questions_per_quiz": 10, "quiz_set_mode": "preset"},
    "study-2": {"mode": "all_variants", "questions_per_quiz": 5, "quiz_set_mode": "balanced_random"},
}


class Cursor:
    def __init__(self, cursor, transform=lambda x: x):
        self.cursor, self.transform = cursor, transform

    def __iter__(self):
        return self

    def __next__(self):
        return self.transform(next(self.cursor))

    def sort(self, *args, **kwargs):
        self.cursor.sort(*args, **kwargs)
        return self

    def skip(self, *args, **kwargs):
        self.cursor.skip(*args, **kwargs)
        return self

    def limit(self, *args, **kwargs):
        self.cursor.limit(*args, **kwargs)
        return self


class StudyCollection:
    def __init__(self, db, raw):
        self.database, self.raw = db, raw

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def tag(self, doc):
        return {**doc, "study_id": self.database.study_id} if doc is not None else None

    def find(self, *args, **kwargs):
        return Cursor(self.raw.find(*args, **kwargs), self.tag)

    def find_one(self, *args, **kwargs):
        return self.tag(self.raw.find_one(*args, **kwargs))

    def insert_one(self, doc, *args, **kwargs):
        doc["study_id"] = self.database.study_id
        return self.raw.insert_one(doc, *args, **kwargs)

    def insert_many(self, docs, *args, **kwargs):
        docs = list(docs)
        for doc in docs:
            doc["study_id"] = self.database.study_id
        return self.raw.insert_many(docs, *args, **kwargs)

    def replace_one(self, query, doc, *args, **kwargs):
        return self.raw.replace_one(query, self.tag(doc), *args, **kwargs)


class StudyUsers(StudyCollection):
    def overlay(self, user):
        if not user:
            return None
        if self.database.study_id == "study-1":
            return self.tag(user)
        enrollment = self.database.raw["study_enrollments"].find_one({"_id": user["_id"]})
        if not enrollment and not user.get("is_admin"):
            return None
        # Never inherit Study 1 consent, assignments, or completion flags.
        return {**{key: value for key, value in user.items() if key in GLOBAL_FIELDS or key == "_id"},
                **(enrollment or {}), "study_id": "study-2"}

    def find_one(self, query=None, projection=None, **kwargs):
        return self.overlay(self.raw.find_one(query or {}, **kwargs))

    def find(self, query=None, projection=None, **kwargs):
        cursor = self.raw.find(query or {}, **kwargs)
        if self.database.study_id == "study-1":
            return Cursor(cursor, self.tag)
        enrolled = {e["_id"] for e in self.database.raw["study_enrollments"].find({})}
        # Use Mongo filtering/sorting before the overlay. Callers search global
        # identity fields; enrollment CAS filters are handled in update_one.
        return iter(self.overlay(user) for user in cursor if user["_id"] in enrolled)

    def count_documents(self, query, **kwargs):
        return int(self.find_one(query) is not None) if "_id" in query else len(list(self.find(query)))

    def update_one(self, query, update, **kwargs):
        if self.database.study_id == "study-1":
            return self.raw.update_one(query, update, **kwargs)
        if set(update) - {"$set", "$unset", "$addToSet", "$pull", "$inc", "$setOnInsert"}:
            raise ValueError("Unsupported enrollment update")
        identity_query = {k: v for k, v in query.items() if k in GLOBAL_FIELDS or k == "_id"}
        user = self.raw.find_one(identity_query)
        if not user:
            return SimpleNamespace(matched_count=0, modified_count=0)
        global_update, progress_update = {}, {}
        for operator, fields in update.items():
            for key, value in fields.items():
                target = global_update if key.split(".")[0] in GLOBAL_FIELDS else progress_update
                target.setdefault(operator, {})[key] = value
        progress_query = {k: v for k, v in query.items() if k not in GLOBAL_FIELDS}
        progress_query["_id"] = user["_id"]
        result = None
        if progress_update:
            result = self.database.raw["study_enrollments"].update_one(progress_query, progress_update,
                upsert=kwargs.get("upsert", False))
            if not result.matched_count and not result.upserted_id:
                return result
        if global_update:
            result = self.raw.update_one({"_id": user["_id"]}, global_update)
        return result or SimpleNamespace(matched_count=1, modified_count=0)

    def find_one_and_update(self, query, update, return_document=ReturnDocument.BEFORE, **kwargs):
        before = self.find_one(query)
        if before is None:
            return None
        result = self.update_one(query, update, **kwargs)
        if not result.matched_count:
            return None
        return self.find_one({"_id": before["_id"]}) if return_document else before


class StudyDatabase:
    def __init__(self, raw, study_id):
        if study_id not in STUDY_IDS:
            raise ValueError("Unknown study")
        self.raw, self.study_id = raw, study_id

    def __getitem__(self, name):
        if name == "users":
            return StudyUsers(self, self.raw["users"])
        if name in SHARED_COLLECTIONS:
            return self.raw[name]
        if name == "survey_items" and self.study_id == "study-2":
            initialize_survey_bank(self.raw)
        physical = name if self.study_id == "study-1" else f"study2__{name}"
        return StudyCollection(self, self.raw[physical])


def raw_database(db):
    return db.raw if isinstance(db, StudyDatabase) else db


def snapshot_legacy_protocol(db, doc):
    """Snapshot once at authentication; keep already drawn quiz sizes intact."""
    if not isinstance(db, StudyDatabase) or doc.get("study_protocol") is not None:
        return doc
    from .study_flow import load_study_config
    protocol = load_study_config(db).as_dict()
    saved = db["quiz_attempts"].find_one({"user_id": str(doc["_id"])})
    if saved and saved.get("question_order"):
        protocol["questions_per_quiz"] = len(saved["question_order"])
    db["users"].update_one({"_id": doc["_id"], "study_protocol": {"$exists": False}},
                            {"$set": {"study_protocol": protocol}})
    return db["users"].find_one({"_id": doc["_id"]})


def initialize_studies(raw):
    raw["study_enrollments"].create_index("approved")
    for sid in STUDY_IDS:
        db = StudyDatabase(raw, sid)
        db["study_config"].update_one({"_id": "active_flow"}, {"$setOnInsert": {
            **PROFILES[sid], "variant_order": ["followup", "double", "links"], "counterbalance": True,
            "version": 1, "quiz_set_map": {}, "wrong_ai_count": 3, "wrong_ai_rate": None,
            "requires_study1_completion": sid == "study-2",
        }}, upsert=True)
    initialize_survey_bank(raw)


def initialize_survey_bank(raw):
    marker = {"_id": "survey_bank_initialized"}
    config = raw["study2__study_config"]
    if config.find_one(marker) or not raw["survey_items"].count_documents({}):
        return
    for item in raw["survey_items"].find({}):
        raw["study2__survey_items"].update_one({"_id": item["_id"]}, {"$setOnInsert": {
            **item, "study_id": "study-2"}}, upsert=True)
    config.update_one(marker, {"$setOnInsert": {"initialized_at": datetime.now(timezone.utc)}}, upsert=True)


def study1_complete(raw, user):
    from .study_flow import ensure_user_flow, reconcile_saved_progress
    doc = reconcile_saved_progress(StudyDatabase(raw, "study-1"), ensure_user_flow(StudyDatabase(raw, "study-1"), user))
    order = doc.get("step_order") or []
    return bool(order) and set(order) <= set(doc.get("completed_steps") or [])


def check_access(raw, user, study_id):
    if study_id == "study-1" or user.get("is_admin"):
        return
    enrollment = raw["study_enrollments"].find_one({"_id": user["_id"]})
    if not enrollment or not enrollment.get("approved"):
        raise HTTPException(403, "Study 2 is available during your interview after administrator approval")
    required = enrollment.get("requires_study1_completion", True)
    if required and not study1_complete(raw, user):
        raise HTTPException(403, "Complete Study 1 before starting Study 2")


def enrollment_status(raw, user, study_id):
    from .study_flow import ensure_user_flow, reconcile_saved_progress
    enrollment = raw["study_enrollments"].find_one({"_id": user["_id"]}) or {}
    approved = study_id == "study-1" or bool(enrollment.get("approved")) or bool(user.get("is_admin"))
    doc = StudyDatabase(raw, study_id)["users"].find_one({"_id": user["_id"]}) if approved else None
    if doc and study_id == "study-1":
        doc = reconcile_saved_progress(StudyDatabase(raw, study_id), ensure_user_flow(StudyDatabase(raw, study_id), doc))
    order = (doc or {}).get("step_order") or []
    completed = len(set((doc or {}).get("completed_steps") or []) & set(order))
    finished = bool(order) and completed == len(order)
    eligible, reason = approved, None
    if not approved:
        reason = "Available during your interview"
    elif study_id == "study-2" and not user.get("is_admin") and enrollment.get("requires_study1_completion", True) and not study1_complete(raw, user):
        eligible, reason = False, "Complete Study 1 first"
    return {"study_id": study_id, "label": "Study 1" if study_id == "study-1" else "Study 2",
        "approved": approved, "available": eligible, "reason": reason,
        "status": "completed" if finished else "in_progress" if (doc or {}).get("started_at") or completed else "approved" if approved else "not_approved",
        "completed_steps": completed, "total_steps": len(order), "finished": finished,
        "consent_required": study_id == "study-2" and not user.get("is_admin") and (
            not (doc or {}).get("consent_agreed_at") or bool((doc or {}).get("consent_declined_at")) or (doc or {}).get("consent") is False),
        "approved_at": enrollment.get("approved_at") if study_id == "study-2" else None,
        "interview_at": enrollment.get("interview_at") if study_id == "study-2" else None}


def ensure_admin_preview(raw, user):
    """Admin previews do not consume participant counterbalancing slots."""
    from .study_flow import load_study_config, build_step_order, quiz_ids_in_order
    db = StudyDatabase(raw, "study-2")
    config = load_study_config(db)
    order = build_step_order(config.variant_order if config.mode == "all_variants" else config.variant_order[:1])
    raw["study_enrollments"].update_one({"_id": user["_id"]}, {"$setOnInsert": {
        "user_id": str(user["_id"]), "study_id": "study-2", "approved": True,
        "admin_preview": True, "consent": True, "consent_agreed_at": datetime.now(timezone.utc),
        "study_protocol": config.as_dict(), "study_flow_version": config.version,
        "study_flow_mode": config.mode, "step_order": order, "completed_steps": [],
        "variant_sequence": list(config.variant_order), "assigned_var": config.variant_order[0],
        "quiz_set_assignment": dict(zip(quiz_ids_in_order(order), ("a", "b", "c", "d"))),
        "progress_reconciled_version": 1,
    }}, upsert=True)


def approve_study2(raw, user_id, admin_id, approved, interview_at=None, notes=""):
    from .study_flow import assign_flow, load_study_config
    if not ObjectId.is_valid(user_id):
        raise HTTPException(404, "Participant not found")
    user = raw["users"].find_one({"_id": ObjectId(user_id)})
    if not user or user.get("is_admin"):
        raise HTTPException(404, "Participant not found")
    now = datetime.now(timezone.utc)
    # First approval freezes the full protocol. A re-grant preserves progress.
    enrollment = raw["study_enrollments"].find_one({"_id": user["_id"]})
    if approved and not (enrollment or {}).get("step_order"):
        db = StudyDatabase(raw, "study-2")
        config = load_study_config(db)
        flow = assign_flow(db)
        try:
            raw["study_enrollments"].update_one({"_id": user["_id"], "step_order": {"$exists": False}}, {"$set": {
                **flow, "user_id": user_id, "study_id": "study-2", "approved": False,
                "consent": False, "completed_steps": [], "requires_study1_completion": config.requires_study1_completion,
                "created_at": now,
            }}, upsert=enrollment is None)
        except DuplicateKeyError:
            # Another administrator froze the same enrollment concurrently.
            # Keep their snapshot instead of replacing it or failing the grant.
            pass
    # Atomically append the audit record with the access change.
    change = {"approved": approved, "admin_id": admin_id, "at": now, "notes": notes,
              "interview_at": interview_at}
    raw["study_enrollments"].update_one({"_id": user["_id"]}, {
        "$set": {"approved": approved, "approved_at" if approved else "revoked_at": now,
                 "approved_by" if approved else "revoked_by": admin_id,
                 "interview_at": interview_at, "interviewer_notes": notes},
        "$push": {"access_history": change},
        "$setOnInsert": {"user_id": user_id, "study_id": "study-2", "created_at": now},
    }, upsert=True)
    return enrollment_status(raw, user, "study-2")
