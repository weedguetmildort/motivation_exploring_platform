from pydantic import BaseModel
from typing import List

class QuestionChoice(BaseModel):
    id: str
    label: str

class QuestionCreate(BaseModel):
    stem: str
    subtitle: str | None = None
    choices: List[QuestionChoice]
    correct_choice_id: str

class QuestionPublic(BaseModel):
    id: str
    stem: str
    subtitle: str | None = None
    choices: List[QuestionChoice]

class QuestionAdminPublic(QuestionPublic):
    correct_choice_id: str

class QuestionUpdate(QuestionCreate):
    pass