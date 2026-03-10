# backend/app/services/chat.py
from pymongo.collection import Collection

_LABELS = ["A", "B", "C", "D"]


def _format_assistant(content) -> str:
    """Combine one or more agent replies into a single assistant message string."""
    if isinstance(content, list):
        if len(content) > 1:
            parts = [
                f"[AGENT {_LABELS[i] if i < len(_LABELS) else str(i + 1)}] {reply}"
                for i, reply in enumerate(content)
            ]
            return "\n\n".join(parts)
        return content[0] if content else ""
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
    """Return the full conversation history as alternating user/assistant messages.

    Agent replies (stored as a list) are combined into a single assistant message
    to satisfy the OpenAI alternating-role requirement:
        [AGENT A] reply1

        [AGENT B] reply2
    """
    docs = list(messages_col.find(
        {"conversation_id": conv_id},
        sort=[("created_at", 1)],  # chronological order
    ))

    history = []
    labels = ["A", "B", "C", "D"]
    for doc in docs:
        role = doc["role"]
        content = doc["content"]
        if role == "user":
            history.append({"role": "user", "content": content})
        elif role == "assistant":
            if isinstance(content, list):
                parts = [
                    f"[AGENT {labels[i] if i < len(labels) else str(i + 1)}] {reply}"
                    for i, reply in enumerate(content)
                ]
                combined = "\n\n".join(parts)
            else:
                combined = content
            history.append({"role": "assistant", "content": combined})

    return history
