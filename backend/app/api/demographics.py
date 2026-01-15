from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel, Field
from bson.objectid import ObjectId
from typing import Optional, List
from datetime import datetime
from ..schemas.user import UserPublic
from .auth import get_current_user

router = APIRouter(prefix="/demographics", tags=["demographics"])

class DemographicsPayload(BaseModel):
    gender: str
    otherGender: Optional[str] = None
    race_ethnicity: List[str] = Field(default_factory=list)
    year: str
    major: Optional[str] = None



# @router.post("/me")
# def save_my_demographics(
#     data: DemographicsPayload,
#     request: Request,
#     user: UserPublic = Depends(get_current_user),
# ):
#     db = request.app.state.db
#     users = db["users"]

#     result = users.update_one(
#       {"_id": user.id if False else {"$eq": None}},  # placeholder; see below
#     )

@router.post("/me")
def save_my_demographics(
    data: DemographicsPayload,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    db = request.app.state.db
    users = db["users"]

    result = users.update_one(
        {"_id": ObjectId(user.id)},
        {
            "$set": {
                "demographics": data.dict(),
                "demographics_completed": True,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return {"ok": True}
