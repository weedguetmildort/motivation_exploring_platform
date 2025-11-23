from typing import Optional
from datetime import datetime
from bson.objectid import ObjectId
from pymongo.collection import Collection
from ..schemas.user import UserPublic
from ..core.security import hash_password, verify_password

def _to_public(doc: dict) -> UserPublic:
    return UserPublic(
        id=str(doc["_id"]),
        email=doc["email"],
        is_admin=doc.get("is_admin"),
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
    }
    res = users.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _to_public(doc)

def find_user_by_email(users: Collection, email: str) -> Optional[dict]:
    return users.find_one({"email": email.lower()})

def check_user_password(user_doc: dict, password: str) -> bool:
    return verify_password(password, user_doc["password_hash"])
