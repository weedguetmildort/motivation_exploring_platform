from datetime import datetime
from bson.objectid import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import get_current_user
from ..schemas.user import UserPublic

router = APIRouter(prefix="/quiz-survey", tags=["quiz-survey"])

class QuizPreSurveyPayload(BaseModel):
    # Q1 – prior experience (Likert 1–5)
    prior_experience: int = Field(ge=1, le=5)

    # Q2 – trust items (Likert 1–5 each)
    trust_rely: int = Field(ge=1, le=5)
    trust_general: int = Field(ge=1, le=5)
    trust_count_on: int = Field(ge=1, le=5)

@router.post("/me")
def save_quiz_pre_survey(
    data: QuizPreSurveyPayload,
    request: Request,
    user: UserPublic = Depends(get_current_user),
):
    db = request.app.state.db
    surveys = db["quiz_pre_surveys"]
    users = db["users"]

    # Insert or upsert survey doc for this user
    surveys.update_one(
        {"user_id": ObjectId(user.id)},
        {
            "$set": {
                "user_id": ObjectId(user.id),
                "responses": data.dict(),
                "updated_at": datetime.utcnow(),
            },
            "$setOnInsert": {"created_at": datetime.utcnow()},
        },
        upsert=True,
    )

    # Mark the user as having completed the quiz pre-survey
    users.update_one(
        {"_id": ObjectId(user.id)},
        {
            "$set": {
                "quiz_pre_survey_completed": True,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    return {"ok": True}