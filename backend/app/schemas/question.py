from pydantic import BaseModel
from typing import List, Optional, Literal


# The set a question belongs to. `null` = unassigned (backward-compatible default).
SetId = Literal["a", "b", "c", "d"]

# AI/admin-estimated difficulty level.
Difficulty = Literal["easy", "medium", "hard"]

# Who last set the difficulty. `null` = never judged.
DifficultySource = Literal["ai", "manual"]


# A single answer choice within a question.
class QuestionChoice(BaseModel):
    id: str     # short key, e.g. "a", "b", "c", "d"
    label: str  # display text shown to the user


# Payload sent by an admin when creating a new question.
class QuestionCreate(BaseModel):
    stem: str                   # the main question text (used as the topic label)
    subtitle: str | None = None # optional clarifying text shown below the stem (the question body)
    choices: List[QuestionChoice]
    correct_choice_id: str      # id of the correct QuestionChoice
    set: Optional[SetId] = None # optional set assignment at creation time


# Question data returned to a regular (non-admin) user during a quiz.
# Does not expose the correct answer.
class QuestionPublic(BaseModel):
    id: str
    stem: str
    subtitle: str | None = None
    choices: List[QuestionChoice]


# Question data returned to admins; extends QuestionPublic with the correct answer
# plus set/difficulty metadata used by the questions panel.
class QuestionAdminPublic(QuestionPublic):
    correct_choice_id: str
    set: Optional[SetId] = None
    difficulty: Optional[Difficulty] = None
    difficulty_source: Optional[DifficultySource] = None
    difficulty_checked: bool = False


# Payload sent by an admin when editing an existing question's content.
class QuestionUpdate(QuestionCreate):
    pass


# Body for assigning (or clearing) a question's set.
class SetAssign(BaseModel):
    set: Optional[SetId] = None


# Body for manually overriding (or clearing) a question's difficulty.
class DifficultyOverride(BaseModel):
    difficulty: Optional[Difficulty] = None
