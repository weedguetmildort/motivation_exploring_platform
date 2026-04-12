# backend/app/services/followup.py
from typing import AsyncGenerator, Callable


async def generate_followup_questions(
    last_ai_message: str,
    get_stream: Callable[[list[dict]], AsyncGenerator[str, None]],
) -> AsyncGenerator[str, None]:
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

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    async for delta in get_stream(messages):
        yield delta
