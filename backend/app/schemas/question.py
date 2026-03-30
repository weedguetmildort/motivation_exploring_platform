from pydantic import BaseModel
from typing import List


# A single answer choice within a question.
class QuestionChoice(BaseModel):
    id: str     # short key, e.g. "a", "b", "c", "d"
    label: str  # display text shown to the user


# Payload sent by an admin when creating a new question.
class QuestionCreate(BaseModel):
    stem: str                   # the main question text
    subtitle: str | None = None # optional clarifying text shown below the stem
    choices: List[QuestionChoice]
    correct_choice_id: str      # id of the correct QuestionChoice


# Question data returned to a regular (non-admin) user during a quiz.
# Does not expose the correct answer.
class QuestionPublic(BaseModel):
    id: str
    stem: str
    subtitle: str | None = None
    choices: List[QuestionChoice]


# Question data returned to admins; extends QuestionPublic with the correct answer.
class QuestionAdminPublic(QuestionPublic):
    correct_choice_id: str


# Payload sent by an admin when editing an existing question. Same fields as creation.
class QuestionUpdate(QuestionCreate):
    pass
