# backend/app/services/chat.py
from pymongo.collection import Collection


def _format_assistant(content) -> str:
    """Combine agent replies into a single assistant message string.
    Labels are pre-baked into each item at save time (e.g. '[AGENT A] ...').
    """
    if isinstance(content, list):
        return "\n\n".join(content) if content else ""
    return content


def get_last_exchange(messages_col: Collection, conv_id: str) -> list[dict]:
    """Return only the most recent user/assistant exchange (1 turn) to save tokens.

    Anchors on the last assistant message's timestamp, then finds the user message
    that preceded it. This guarantees a properly paired exchange even if the current
    user message has already been inserted into the collection.
    """
    last_asst = messages_col.find_one(
        {"conversation_id": conv_id, "role": "assistant"},
        sort=[("created_at", -1)],
    )
    if not last_asst:
        return []

    last_user = messages_col.find_one(
        {
            "conversation_id": conv_id,
            "role": "user",
            "created_at": {"$lt": last_asst["created_at"]},
        },
        sort=[("created_at", -1)],
    )
    if not last_user:
        return []

    return [
        {"role": "user", "content": last_user["content"]},
        {"role": "assistant", "content": _format_assistant(last_asst["content"])},
    ]


def get_conversation_history(messages_col: Collection, conv_id: str) -> list[dict]:
    """Return all raw message documents for a conversation in chronological order."""
    return list(messages_col.find(
        {"conversation_id": conv_id},
        sort=[("created_at", 1)],
    ))
