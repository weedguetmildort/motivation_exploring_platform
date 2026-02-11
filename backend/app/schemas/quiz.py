# backend/app/schemas/quiz.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class QuizAnswerRecord(BaseModel):
    question_id: str
    shown_at: datetime
    answered_at: Optional[datetime] = None
    choice_id: Optional[str] = None

class QuizAttemptStatus(str):
    # not an actual Enum class to keep it simple for now
    pass

class QuizAttemptPublic(BaseModel):
    quiz_id: str
    status: str  # "in_progress" or "completed"
    total_questions: int
    answered_count: int

class QuizQuestionPayload(BaseModel):
    id: str
    stem: str
    subtitle: Optional[str] = None
    choices: List[dict]  # { id: str, label: str }


class QuizStateResponse(BaseModel):
    attempt: QuizAttemptPublic
    current_question: Optional[QuizQuestionPayload] = None

#What frontend must send to FastAPI when user submits an answer
class SubmitAnswerRequest(BaseModel):
    question_id: str
    choice_id: str
