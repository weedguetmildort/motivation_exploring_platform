# backend/app/services/chat.py
import re
from typing import Optional
from pymongo.collection import Collection


def _format_assistant(content) -> str:
    """Combine agent replies into a single assistant message string.
    Labels are pre-baked into each item at save time (e.g. '[AGENT A] ...').
    """
    if isinstance(content, list):
        return "\n\n".join(content) if content else ""
    return content


def get_last_exchange(
    messages_col: Collection,
    conv_id: str,
    agent_prefix: Optional[str] = None,
) -> list[dict]:
    """Return the most recent user/assistant exchange (1 turn) to save tokens.

    Anchors on the last assistant message's timestamp, then finds the user message
    that preceded it. This guarantees a properly paired exchange even if the current
    user message has already been inserted into the collection.

    agent_prefix: if provided (e.g. '[AGENT A]'), finds the last assistant doc that
    actually contains that agent's reply (skipping turns where only the other agent
    responded), extracts only that agent's text, and strips the prefix before returning.
    This means a globally-addressed turn is still visible to all agents, while an
    @-mentioned turn is only visible to the addressed agent.
    """
    if agent_prefix:
        # Only consider assistant docs where this agent actually replied.
        # $elemMatch matches array docs; the regex anchors to the start of each element.
        asst_query = {
            "conversation_id": conv_id,
            "role": "assistant",
            "content": {"$elemMatch": {"$regex": f"^{re.escape(agent_prefix)}"}},
        }
    else:
        asst_query = {"conversation_id": conv_id, "role": "assistant"}

    last_asst = messages_col.find_one(asst_query, sort=[("created_at", -1)])
    if not last_asst:
        return []

    content = last_asst["content"]
    if agent_prefix and isinstance(content, list):
        matches = [c for c in content if c.startswith(agent_prefix)]
        asst_content = matches[0][len(agent_prefix):].strip() if matches else _format_assistant(content)
    else:
        asst_content = _format_assistant(content)

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
        {"role": "assistant", "content": asst_content},
    ]


def get_conversation_history(messages_col: Collection, conv_id: str) -> list[dict]:
    """Return all raw message documents for a conversation in chronological order."""
    return list(messages_col.find(
        {"conversation_id": conv_id},
        sort=[("created_at", 1)],
    ))
