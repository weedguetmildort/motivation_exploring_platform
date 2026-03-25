# backend/app/services/users.py
from typing import Optional
from datetime import datetime, timezone
from pymongo.collection import Collection
from pymongo import ReturnDocument

from ..schemas.user import UserPublic, SurveyStage, AssignedVar
from ..core.security import hash_password, verify_password


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
        assigned_var=doc.get("assigned_var", AssignedVar.followup.value),
        is_admin=bool(doc.get("is_admin", False)),
        demographics_completed=doc.get("demographics_completed", False),
        survey_pre_base_completed=doc.get("survey_pre_base_completed", False),
        quiz_base_completed=doc.get("quiz_base_completed", False),
        survey_post_base_completed=doc.get("survey_post_base_completed", False),
        quiz_variant_completed=doc.get("quiz_variant_completed", False),
        survey_post_variant_completed=doc.get("survey_post_variant_completed", False),
        survey_stage=_normalize_stage(doc.get("survey_stage")),
    )


def get_users_collection(db) -> Collection:
    return db["users"]


def ensure_indexes(users: Collection) -> None:
    users.create_index("email", unique=True)


def _next_assigned_var(users: Collection) -> str:
    assigned_vars = [
        AssignedVar.followup.value,
        AssignedVar.double.value,
        AssignedVar.links.value,
    ]
    counters = users.database["counters"]
    counter_doc = counters.find_one_and_update(
        {"_id": "user_signup_round_robin"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    seq = int(counter_doc.get("seq", 1))
    return assigned_vars[(seq - 1) % len(assigned_vars)]


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
    }

    res = users.insert_one(doc)
    doc["_id"] = res.inserted_id

    assigned_var = _next_assigned_var(users)
    users.update_one({"_id": doc["_id"]}, {"$set": {"assigned_var": assigned_var}})
    doc["assigned_var"] = assigned_var

    return _to_public(doc)


def find_user_by_email(users: Collection, email: str) -> Optional[dict]:
    return users.find_one({"email": email.lower()})


def check_user_password(user_doc: dict, password: str) -> bool:
    return verify_password(password, user_doc["password_hash"])
