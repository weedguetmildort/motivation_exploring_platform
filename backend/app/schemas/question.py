from pydantic import BaseModel
from typing import List

class QuestionChoice(BaseModel):
    id: str
    label: str

class QuestionCreate(BaseModel):
    stem: str
    subtitle: str | None = None
    choices: List[QuestionChoice]

class QuestionPublic(QuestionCreate):
    id: str

class QuestionUpdate(QuestionCreate):
    pass