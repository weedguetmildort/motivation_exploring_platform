# backend/app/services/users.py
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from pymongo.collection import Collection
from pymongo import ReturnDocument

from ..schemas.user import UserPublic, SurveyStage, AssignedVar
from ..core.security import hash_password, verify_password
from . import study_flow

_HEARTBEAT_DEBOUNCE = timedelta(minutes=2)


def _normalize_stage(raw) -> SurveyStage:
    """
    Ensure survey_stage is always a valid enum value.
    Protects against legacy or bad data in Mongo.
    """
    if isinstance(raw, SurveyStage):
        return raw

    if isinstance(raw, str):
        try:
            return SurveyStage(raw)
        except ValueError:
            pass

    return SurveyStage.pre_base


def _to_public(doc: dict) -> UserPublic:
    return UserPublic(
        id=str(doc["_id"]),
        email=doc["email"],
        first_name=doc.get("first_name"),
        last_name=doc.get("last_name"),
        consent=doc.get("consent"),
        consent_given_at=doc.get("consent_given_at"),
        consent_text=doc.get("consent_text"),
        consent_agreed_at=doc.get("consent_agreed_at"),
        consent_declined_at=doc.get("consent_declined_at"),
        consent_viewed_at=doc.get("consent_viewed_at"),
        consent_abandoned_at=doc.get("consent_abandoned_at"),
        last_active_at=doc.get("last_active_at"),
        assigned_var=doc.get("assigned_var", AssignedVar.followup.value),
        is_admin=bool(doc.get("is_admin", False)),
        demographics_completed=doc.get("demographics_completed", False),
        step_order=list(doc.get("step_order") or []),
        completed_steps=list(doc.get("completed_steps") or []),
        variant_sequence=list(doc.get("variant_sequence") or []),
        study_flow_version=int(doc.get("study_flow_version", 1)),
        survey_pre_base_completed=doc.get("survey_pre_base_completed", False),
        quiz_base_completed=doc.get("quiz_base_completed", False),
        survey_post_base_completed=doc.get("survey_post_base_completed", False),
        quiz_variant_completed=doc.get("quiz_variant_completed", False),
        survey_post_variant_completed=doc.get("survey_post_variant_completed", False),
        survey_stage=_normalize_stage(doc.get("survey_stage")),
        quiz_sets=doc.get("quiz_sets"),
        followup_study_granted=doc.get("followup_study_granted", False),
    )


def get_users_collection(db) -> Collection:
    return db["users"]


def ensure_indexes(users: Collection) -> None:
    users.create_index("email", unique=True)


_ASSIGNED_VARS = [
    AssignedVar.followup.value,
    AssignedVar.double.value,
    AssignedVar.links.value,
]

_NEXT_OVERRIDE_ID = "next_assignment_override"
_ROUND_ROBIN_ID = "user_signup_round_robin"
_QUIZ_DEFAULT_SETS_ID = "quiz_default_sets"


def _next_assigned_var(users: Collection) -> str:
    counters = users.database["counters"]
    counter_doc = counters.find_one_and_update(
        {"_id": _ROUND_ROBIN_ID},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    seq = int(counter_doc.get("seq", 1))
    return _ASSIGNED_VARS[(seq - 1) % len(_ASSIGNED_VARS)]


def set_next_assignment_override(users: Collection, variant: Optional[str]) -> None:
    """Admin control: force the next sign-up into ``variant`` (one-shot), or
    clear the override with ``None`` to fall back to round-robin rotation."""
    counters = users.database["counters"]
    counters.update_one(
        {"_id": _NEXT_OVERRIDE_ID},
        {"$set": {"variant": variant}},
        upsert=True,
    )


def _consume_next_override(users: Collection) -> Optional[str]:
    """Atomically claim and clear a pending one-shot override, if any.

    Uses find_one_and_update so two concurrent sign-ups can't both claim it —
    only the first sees a non-null ``variant``.
    """
    counters = users.database["counters"]
    doc = counters.find_one_and_update(
        {"_id": _NEXT_OVERRIDE_ID, "variant": {"$ne": None}},
        {"$set": {"variant": None}},
        return_document=ReturnDocument.BEFORE,
    )
    if doc and doc.get("variant"):
        return doc["variant"]
    return None


def peek_next_assignment(users: Collection) -> dict:
    """What condition the next sign-up will receive, without consuming anything.

    Returns the pending override if set, else the value round-robin would hand
    out next (derived from the current counter without incrementing it).
    """
    counters = users.database["counters"]

    override = counters.find_one({"_id": _NEXT_OVERRIDE_ID})
    if override and override.get("variant"):
        return {"next": override["variant"], "source": "override"}

    counter = counters.find_one({"_id": _ROUND_ROBIN_ID})
    seq = int(counter.get("seq", 0)) if counter else 0
    return {"next": _ASSIGNED_VARS[seq % len(_ASSIGNED_VARS)], "source": "rotation"}


# ── Quiz set restriction (Phase 11) ──────────────────────────────────────────

def get_quiz_default_sets(users: Collection) -> Optional[List[str]]:
    """The global default question set(s) stamped onto new sign-ups.

    Returns ``None`` when no default is configured (participants draw from all
    questions).
    """
    counters = users.database["counters"]
    doc = counters.find_one({"_id": _QUIZ_DEFAULT_SETS_ID})
    sets = doc.get("sets") if doc else None
    # Only honor an actual non-empty list; anything else = no restriction.
    if not isinstance(sets, list) or not sets:
        return None
    return sets


def set_quiz_default_sets(users: Collection, sets: Optional[List[str]]) -> None:
    """Admin control: set the global default question set(s) for new sign-ups.
    ``None``/empty clears the restriction."""
    counters = users.database["counters"]
    counters.update_one(
        {"_id": _QUIZ_DEFAULT_SETS_ID},
        {"$set": {"sets": sets or None}},
        upsert=True,
    )


def set_participant_quiz_sets(
    users: Collection, user_id: str, sets: Optional[List[str]]
) -> Optional[dict]:
    """Override one participant's allowed question set(s). ``None``/empty clears
    the restriction. Returns the updated user doc, or ``None`` if not found."""
    return users.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": {"quiz_sets": sets or None, "updated_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )


def set_participant_followup_study(
    users: Collection, user_id: str, granted: bool
) -> Optional[dict]:
    """Grant/revoke a participant's follow-up study access (Phase 13). Returns
    the updated user doc, or ``None`` if not found."""
    return users.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": {"followup_study_granted": granted, "updated_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )


def create_user(
    users: Collection,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    consent: bool,
) -> UserPublic:
    if consent is not True:
        raise ValueError("Consent is required")

    now = datetime.now(timezone.utc)

    doc = {
        "email": email.strip().lower(),
        "password_hash": hash_password(password),
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "consent": True,
        "consent_given_at": now,
        "created_at": now,
        "updated_at": now,
        "is_admin": False,
        "demographics_completed": False,
        "survey_pre_base_completed": False,
        "quiz_base_completed": False,
        "survey_post_base_completed": False,
        "quiz_variant_completed": False,
        "survey_post_variant_completed": False,
        "survey_stage": SurveyStage.pre_base.value,
        "demographics": {},
        "step_order": [],
        "completed_steps": [],
        "variant_sequence": [],
        # Stamp the current global default set restriction (None = unrestricted).
        "quiz_sets": get_quiz_default_sets(users),
    }

    res = users.insert_one(doc)
    doc["_id"] = res.inserted_id

    # Participants now work through every variant, so assignment resolves a whole
    # counterbalanced *sequence* rather than a single condition. A one-shot admin
    # override still wins: it pins the first variant and, as before, does not
    # advance the round-robin counter, so rotation resumes cleanly after.
    flow = study_flow.assign_flow(db=users.database, forced_first=_consume_next_override(users))
    users.update_one({"_id": doc["_id"]}, {"$set": flow})
    doc.update(flow)

    return _to_public(doc)


def maybe_touch_last_active(users: Collection, user_doc: dict) -> None:
    """Update last_active_at only if more than _HEARTBEAT_DEBOUNCE has passed
    since the last recorded value, to avoid a write on every single
    authenticated request (get_current_user runs on every one).
    """
    now = datetime.now(timezone.utc)
    last = user_doc.get("last_active_at")
    if last is not None:
        # pymongo returns stored datetimes as naive UTC by default (no tz_aware
        # codec option on this client) — attach tzinfo before subtracting, or a
        # round-tripped value would raise "can't subtract offset-naive and
        # offset-aware datetimes" on every second heartbeat check.
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if (now - last) < _HEARTBEAT_DEBOUNCE:
            return
    users.update_one({"_id": user_doc["_id"]}, {"$set": {"last_active_at": now}})


def find_user_by_email(users: Collection, email: str) -> Optional[dict]:
    return users.find_one({"email": email.lower()})


def check_user_password(user_doc: dict, password: str) -> bool:
    return verify_password(password, user_doc["password_hash"])
