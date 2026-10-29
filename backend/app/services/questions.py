import csv
import io
import re
from bson.objectid import ObjectId
from fastapi import HTTPException
from typing import List, Optional
from datetime import datetime
from pymongo.collection import Collection
from ..schemas.question import (
    ALL_SET_IDS,
    QuestionChoice,
    QuestionCreate,
    QuestionImportIssue,
    QuestionImportReport,
    QuestionPublic,
    QuestionAdminPublic,
    QuestionUpdate,
    SetId,
    Difficulty,
)

def get_questions_collection(db) -> Collection:
    return db["questions"]


def _to_admin_public(doc: dict) -> QuestionAdminPublic:
    """Map a raw Mongo doc to the admin view, backfilling Phase 8 fields for
    legacy documents that predate set/difficulty."""
    return QuestionAdminPublic(
        id=str(doc["_id"]),
        stem=doc["stem"],
        subtitle=doc.get("subtitle"),
        choices=doc["choices"],
        correct_choice_id=doc.get("correct_choice_id", ""),
        set=doc.get("set"),
        difficulty=doc.get("difficulty"),
        difficulty_source=doc.get("difficulty_source"),
        difficulty_checked=doc.get("difficulty_checked", False),
    )


def _new_question_doc(data: QuestionCreate) -> dict:
    """A new question starts unjudged; the AI difficulty pass picks it up."""
    return {
        "stem": data.stem,
        "subtitle": data.subtitle,
        "choices": [c.model_dump() for c in data.choices],
        "correct_choice_id": data.correct_choice_id,
        "set": data.set,
        "difficulty": None,
        "difficulty_source": None,
        "difficulty_checked": False,
        "created_at": datetime.utcnow(),
        "active": True,
    }


def create_question(col: Collection, data: QuestionCreate) -> QuestionAdminPublic:
    doc = _new_question_doc(data)
    res = col.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _to_admin_public(doc)

def list_questions(col: Collection, limit: Optional[int] = None) -> List[QuestionAdminPublic]:
    # The admin panel counts questions per set from this list, so by default it
    # returns the whole bank rather than the newest page.
    docs = col.find().sort("created_at", -1)
    if limit:
        docs = docs.limit(limit)
    return [_to_admin_public(doc) for doc in docs]


# ── CSV import ───────────────────────────────────────────────────────────────

CHOICE_IDS = ("a", "b", "c", "d")
IMPORT_COLUMNS = ("topic", "question", *CHOICE_IDS, "correct", "set")
REQUIRED_IMPORT_COLUMNS = IMPORT_COLUMNS[:-1]  # set may be left out entirely
MAX_IMPORT_ROWS = 2000
# Spreadsheets silently turn answers such as 2/5 or 10/21 into dates, which
# then export as 2/5/2026 or 2026-02-05. No real answer looks like this.
_DATE_LIKE = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?|\d{1,2}-[A-Za-z]{3}(-\d{2,4})?)$")


def _normalized(text) -> str:
    return " ".join(str(text or "").split()).casefold()


def _question_key(stem, subtitle, labels) -> tuple:
    """Questions with the same topic, text and answers (ignoring case and spacing) are duplicates."""
    return _normalized(stem), _normalized(subtitle), tuple(_normalized(label) for label in labels)


def parse_question_csv(text: str) -> tuple[list[tuple[int, QuestionCreate]], list[QuestionImportIssue], int]:
    """Read an import CSV, collecting every problem by spreadsheet row (the header is row 1).

    Returns the valid rows as (row, question), the errors, and the number of
    non-blank data rows read.
    """
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))  # Excel adds a byte-order mark
    questions: list[tuple[int, QuestionCreate]] = []
    errors: list[QuestionImportIssue] = []
    rows = 0
    try:
        header = next(reader, None)
        if not header or not any(name.strip() for name in header):
            return [], [QuestionImportIssue(row=1, message="The file is empty")], 0
        columns = [name.strip().lower() for name in header]
        problems = []
        if unknown := [name for name in columns if name and name not in IMPORT_COLUMNS]:
            problems.append("Unknown column(s): " + ", ".join(unknown))
        if missing := [name for name in REQUIRED_IMPORT_COLUMNS if name not in columns]:
            problems.append("Missing column(s): " + ", ".join(missing))
        if repeated := sorted({name for name in columns if name and columns.count(name) > 1}):
            problems.append("Repeated column(s): " + ", ".join(repeated))
        if problems:
            expected = ", ".join(IMPORT_COLUMNS) + " (set is optional)"
            return [], [QuestionImportIssue(row=1, message=". ".join(problems) + ". Expected: " + expected)], 0

        for row_number, values in enumerate(reader, start=2):
            if not any(value.strip() for value in values):
                continue  # spreadsheets often export trailing blank rows
            rows += 1
            if rows > MAX_IMPORT_ROWS:
                errors.append(QuestionImportIssue(row=row_number, message=f"Import at most {MAX_IMPORT_ROWS} questions per file"))
                break
            cell = {name: (values[index].strip() if index < len(values) else "")
                    for index, name in enumerate(columns) if name}
            problems = []
            if any(value.strip() for value in values[len(columns):]):
                problems.append("the row has more cells than the header")
            if not cell["topic"]:
                problems.append("topic is empty")
            for letter in CHOICE_IDS:
                if not cell[letter]:
                    problems.append(f"choice {letter} is empty")
                elif _DATE_LIKE.match(cell[letter]):
                    problems.append(f"choice {letter} ({cell[letter]!r}) looks like a date; format the answer "
                                    "columns as plain text before exporting")
            correct = cell["correct"].lower()
            if correct not in CHOICE_IDS:
                problems.append(f"correct must be a, b, c or d (found {cell['correct']!r})")
            set_value = cell.get("set", "").lower() or None
            if set_value and set_value not in ALL_SET_IDS:
                problems.append(f"set must be blank or one of {', '.join(ALL_SET_IDS)} (found {cell['set']!r})")
            if problems:
                errors.append(QuestionImportIssue(row=row_number, message="; ".join(problems)))
                continue
            questions.append((row_number, QuestionCreate(
                stem=cell["topic"], subtitle=cell["question"] or None,
                choices=[QuestionChoice(id=letter, label=cell[letter]) for letter in CHOICE_IDS],
                correct_choice_id=correct, set=set_value)))
    except csv.Error as error:
        errors.append(QuestionImportIssue(row=max(reader.line_num, 1), message=f"The file is not valid CSV: {error}"))
    return questions, errors, rows


def import_questions(col: Collection, text: str, dry_run: bool = True) -> QuestionImportReport:
    """Validate a whole CSV and, unless it is a dry run, save its new questions.

    Nothing is saved while any row has an error. Rows matching a question
    already in the bank, or an earlier row of the file, are skipped and reported.
    """
    questions, errors, rows = parse_question_csv(text)
    existing = {_question_key(doc.get("stem"), doc.get("subtitle"), [c.get("label") for c in doc.get("choices") or []])
                for doc in col.find({}, {"stem": 1, "subtitle": 1, "choices": 1})}
    first_row: dict[tuple, int] = {}
    new: list[QuestionCreate] = []
    skipped: list[QuestionImportIssue] = []
    for row, question in questions:
        key = _question_key(question.stem, question.subtitle, [c.label for c in question.choices])
        if key in existing:
            skipped.append(QuestionImportIssue(row=row, message="Already in the question bank; skipped"))
        elif key in first_row:
            skipped.append(QuestionImportIssue(row=row, message=f"Same question as row {first_row[key]}; skipped"))
        else:
            first_row[key] = row
            new.append(question)

    by_set = {**{set_id: 0 for set_id in ALL_SET_IDS}, "unassigned": 0}
    for question in new:
        by_set[question.set or "unassigned"] += 1
    imported = 0
    if not errors and not dry_run and new:
        col.insert_many([_new_question_doc(question) for question in new])
        imported = len(new)
    return QuestionImportReport(dry_run=dry_run, valid=not errors, rows=rows, to_import=len(new),
                                imported=imported, by_set=by_set, errors=errors, skipped=skipped)

def update_question(col, question_id: str, data: QuestionUpdate) -> QuestionAdminPublic:
    try:
        oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question id")

    existing = col.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Question not found")

    # `set` is intentionally NOT written here — it is managed via assign_set so a
    # plain content edit never wipes the assignment.
    update_doc = {
        "stem": data.stem,
        "subtitle": data.subtitle,
        "choices": [c.model_dump() for c in data.choices],
        "correct_choice_id": data.correct_choice_id,
    }

    # Re-judge on edit: reset an AI-assigned difficulty so the next AI pass
    # re-evaluates the changed content. A manual override is preserved.
    if existing.get("difficulty_source") != "manual":
        update_doc["difficulty"] = None
        update_doc["difficulty_source"] = None
        update_doc["difficulty_checked"] = False

    res = col.find_one_and_update(
        {"_id": oid},
        {"$set": update_doc},
        return_document=True,
    )

    if not res:
        raise HTTPException(status_code=404, detail="Question not found")

    return _to_admin_public(res)

def assign_set(col, question_id: str, set_value: Optional[SetId]) -> QuestionAdminPublic:
    try:
        oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question id")

    res = col.find_one_and_update(
        {"_id": oid},
        {"$set": {"set": set_value}},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Question not found")
    return _to_admin_public(res)

def override_difficulty(col, question_id: str, difficulty: Optional[Difficulty]) -> QuestionAdminPublic:
    try:
        oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question id")

    if difficulty is None:
        # Clearing a manual difficulty returns the question to the unjudged pool.
        update_doc = {"difficulty": None, "difficulty_source": None, "difficulty_checked": False}
    else:
        update_doc = {"difficulty": difficulty, "difficulty_source": "manual", "difficulty_checked": True}

    res = col.find_one_and_update(
        {"_id": oid},
        {"$set": update_doc},
        return_document=True,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Question not found")
    return _to_admin_public(res)

def delete_question(col, question_id: str) -> None:
    try:
        oid = ObjectId(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid question id")

    res = col.delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Question not found")
