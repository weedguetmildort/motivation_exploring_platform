# backend/app/services/followup.py
import re
from typing import Callable, Awaitable


async def generate_followup_questions(
    last_ai_message: str,
    get_chat_response: Callable[[list[dict]], Awaitable[str]],
) -> list[str]:
    system_prompt = (
        "You are a helpful assistant who generates short follow-up questions "
        "related ONLY to the explanation you just gave the student. "
        "Your follow-up questions MUST be: directly related to the explanation, "
        "concise (1 sentence, max 12 words), simple and beginner-friendly, "
        "NOT about homework, exams, studying, or general help. "
        "Return ONLY the 3 questions as a numbered list (1., 2., 3.)."
    )
    user_prompt = (
        f"Here is the last thing you told the student:\n\n{last_ai_message}"
        "\n\nGenerate exactly 3 possible follow-up questions the student might ask next."
    )

    raw = await get_chat_response([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

    questions: list[str] = []
    for line in raw.split("\n"):
        trimmed = line.strip()
        if not trimmed:
            continue
        m = re.match(r"^[0-9]+[.)\-:\s]+(.*)", trimmed)
        if m:
            text = m.group(1).strip()
            if text:
                questions.append(text)
    if not questions:
        questions = [raw]
    return questions[:3]
