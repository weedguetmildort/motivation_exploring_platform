# backend/app/services/question_difficulty.py
"""AI difficulty estimation for quiz questions.

Mirrors the fail-open LLM pattern in link_health.llm_judges_relevant: ask the
model for a single-word classification, parse defensively, and on any error
leave the question unjudged so it is retried on the next pass.
"""
from typing import Optional

from openai import OpenAI

from .questions import get_questions_collection
from ..core.llm import get_llm_model

_VALID_LEVELS = ("easy", "medium", "hard")


def llm_judge_difficulty(
    stem: str,
    subtitle: Optional[str],
    choices: list,
    openai_client: OpenAI,
) -> Optional[str]:
    """Classify a question as easy/medium/hard. Returns None on error or an
    unparseable reply (fail-open → the question stays unjudged and is retried)."""
    try:
        choices_text = "; ".join(
            f"{c.get('id')}: {c.get('label')}" for c in (choices or [])
        )
        prompt = (
            "You are classifying the difficulty of a multiple-choice quiz question "
            "for a college-level study on statistics, permutations, and combinations. "
            f"Topic: '{stem}'. Question: '{subtitle or ''}'. Choices: {choices_text}. "
            "Reply with exactly one word: EASY, MEDIUM, or HARD."
        )
        model = get_llm_model()
        resp = openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0,
        )
        answer = (resp.choices[0].message.content or "").strip().lower()
        for level in _VALID_LEVELS:
            if answer.startswith(level):
                return level
        return None
    except Exception as e:
        print(f"[question_difficulty] llm_judge_difficulty error: {e}")
        return None  # fail open — leave unjudged, retry next run


def run_difficulty_judging(db, openai_client: OpenAI, limit: int = 100) -> dict:
    """Judge every question that hasn't been evaluated yet
    (difficulty_checked != True). Returns a summary dict."""
    col = get_questions_collection(db)
    docs = list(col.find({"difficulty_checked": {"$ne": True}}).limit(limit))

    judged = 0
    skipped = 0
    for doc in docs:
        level = llm_judge_difficulty(
            doc.get("stem", ""),
            doc.get("subtitle"),
            doc.get("choices", []),
            openai_client,
        )
        if level is None:
            skipped += 1
            continue
        col.update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "difficulty": level,
                "difficulty_source": "ai",
                "difficulty_checked": True,
            }},
        )
        judged += 1

    return {"judged": judged, "skipped": skipped}
