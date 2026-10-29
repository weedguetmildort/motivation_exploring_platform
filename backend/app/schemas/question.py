from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Literal, get_args


# The set a question belongs to. `null` = unassigned (backward-compatible default).
SetId = Literal["a", "b", "c", "d"]

# The set letters, derived from SetId so there is one source of truth. Adding a
# set means editing SetId alone — study_flow's per-quiz set mapping and its
# reconciliation both read this.
ALL_SET_IDS: tuple[str, ...] = get_args(SetId)

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

    @model_validator(mode="after")
    def _correct_choice_is_offered(self):
        # Shared by the add/edit forms and the CSV import, so all three agree.
        if self.correct_choice_id not in {choice.id for choice in self.choices}:
            raise ValueError("correct_choice_id must be the id of one of the choices")
        return self


# Body for a CSV import. dry_run checks every row and reports what would be
# imported without saving anything.
class QuestionImport(BaseModel):
    csv: str = Field(..., max_length=2_000_000)
    dry_run: bool = True


class QuestionImportIssue(BaseModel):
    row: int      # spreadsheet row number; the header is row 1
    message: str


class QuestionImportReport(BaseModel):
    dry_run: bool
    valid: bool                   # False when any row has an error; nothing is saved then
    rows: int                     # non-blank data rows read
    to_import: int                # new questions (rows minus duplicates)
    imported: int                 # questions actually saved (0 for a dry run or invalid file)
    by_set: dict[str, int]        # new questions per set letter, plus "unassigned"
    errors: List[QuestionImportIssue]
    skipped: List[QuestionImportIssue]  # duplicates, which are not imported


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
