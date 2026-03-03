from typing import Optional
from datetime import datetime
from bson.objectid import ObjectId
from pymongo.collection import Collection
from ..schemas.user import UserPublic, SurveyStage
from ..core.security import hash_password, verify_password

def _normalize_stage(raw) -> str:
    """
    Ensures survey_stage is always a valid value.
    Protects against legacy bad data.
    """
    valid_values = {stage.value for stage in SurveyStage}

    if isinstance(raw, str) and raw in valid_values:
        return raw

    # fallback safely
    return SurveyStage.pre_base.value

def _to_public(doc: dict) -> UserPublic:
    return UserPublic(
        id=str(doc["_id"]),
        email=doc["email"],
        is_admin=bool(doc.get("is_admin", False)),
        demographics_completed=doc.get("demographics_completed", False),
        survey_pre_base_completed=doc.get("survey_pre_base_completed", False),
        quiz_base_completed=doc.get("quiz_base_completed", False),
        survey_post_base_completed=doc.get("survey_post_base_completed", False),
        quiz_variant_completed=doc.get("quiz_variant_completed", False),
        survey_post_variant_completed=doc.get("survey_post_variant_completed", False),
        survey_stage=_normalize_stage(doc.get("survey_stage")),
        # survey_stage=doc.get("survey_stage", SurveyStage.pre_base),
    )

def get_users_collection(db) -> Collection:
    return db["users"]

def ensure_indexes(users: Collection) -> None:
    users.create_index("email", unique=True)

def create_user(users: Collection, email: str, password: str) -> UserPublic:
    doc = {
        "email": email.lower(),
        "password_hash": hash_password(password),
        "created_at": datetime.utcnow(),
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
    return _to_public(doc)

def find_user_by_email(users: Collection, email: str) -> Optional[dict]:
    return users.find_one({"email": email.lower()})

def check_user_password(user_doc: dict, password: str) -> bool:
    return verify_password(password, user_doc["password_hash"])
