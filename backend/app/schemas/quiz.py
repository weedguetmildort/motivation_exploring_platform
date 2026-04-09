# backend/app/schemas/quiz.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


# Tracks a single answer within a quiz attempt, stored as a subdocument in MongoDB.
# shown_at and answered_at allow time-on-question analysis.
class QuizAnswerRecord(BaseModel):
    question_id: str
    shown_at: datetime
    answered_at: Optional[datetime] = None  # None until the user submits an answer
    choice_id: Optional[str] = None         # the answer the user selected
    marked_correct: Optional[bool] = None   # set at submission time by comparing to correct_choice_id
    #TODO: should this also include the correct answer choice?


# Placeholder for quiz attempt status strings ("in_progress", "completed").
# Not a full Enum to keep serialization simple.
class QuizAttemptStatus(str):
    pass


# Summary of a quiz attempt returned to the client, used to render progress indicators.
class QuizAttemptPublic(BaseModel):
    quiz_id: str
    status: str  # "in_progress" or "completed"
    total_questions: int
    answered_count: int
    incorrect_question_ids: list[str] = []


# The question data sent to the client for the current unanswered question.
# Choices are dicts rather than QuestionChoice objects to avoid a cross-schema import.
class QuizQuestionPayload(BaseModel):
    id: str
    stem: str
    subtitle: Optional[str] = None
    choices: List[dict]  # { id: str, label: str }


# Full state of the user's current quiz, returned by GET /quiz/{quiz_id}/state.
# current_question is None when the quiz is completed.
class QuizStateResponse(BaseModel):
    conversation_id: str            # the chat conversation tied to this quiz attempt
    attempt: QuizAttemptPublic
    current_question: Optional[QuizQuestionPayload] = None


# Payload sent by the client when submitting an answer to the current question.
class SubmitAnswerRequest(BaseModel):
    question_id: str
    choice_id: str


# One answered question in the admin results view, including both the user's choice
# and the correct answer with their display labels.
class QuizResultItem(BaseModel):
    question_number: int        # 1-based position in the question_order list
    question_id: str
    stem: str
    user_choice_id: str
    user_choice_label: str
    correct_choice_id: str
    correct_choice_label: str
    is_correct: bool


# Returned by GET /quiz/{quiz_id}/results (admin only).
# Contains score summary and the full per-question breakdown.
class QuizResultsResponse(BaseModel):
    quiz_id: str
    total_questions: int
    correct_count: int
    items: List[QuizResultItem]
