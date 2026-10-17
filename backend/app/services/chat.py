# backend/app/services/chat.py
import re
from typing import Optional
from pymongo.collection import Collection

from ..schemas.question import QuestionChoice


def detect_stated_choice(reply_text: str, choices: list[QuestionChoice]) -> Optional[str]:
    """Heuristic: case-insensitive substring match of each choice's label against
    the leading 300 chars of reply_text (the system prompt forces the AI to name
    its choice up front). Returns the id only on exactly one confident match;
    returns None on zero or ambiguous (2+) matches — never guesses.
    """
    if not choices:
        return None
    window = reply_text[:300].lower()
    matches = [c.id for c in choices if c.label.strip().lower() in window]
    return matches[0] if len(matches) == 1 else None


# Phrases that indicate the reply is narrating the "answer incorrectly" system
# instruction to the participant instead of just following it silently — e.g.
# "since we are to select an incorrect answer, I will confidently choose C."
# Participants must never see that their answer is deliberately wrong, so any
# match here is a prompt-leak worth flagging even though the prompt already
# tells the model not to do this.
_MANIPULATION_LEAK_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"\bwe are (?:to|supposed to|asked to)\b",
        r"\bi(?:'m| am) (?:asked|told|instructed|supposed) to\b",
        r"\binstructed to\b",
        r"\bas instructed\b",
        r"\bmy instructions\b",
        r"\bsystem prompt\b",
        r"\bintentionally (?:incorrect|wrong)\b",
        r"\bdeliberately (?:incorrect|wrong)\b",
        r"\b(?:choose|select|pick|give|provide) an incorrect answer\b",
        r"\bsupposed to (?:be wrong|be incorrect|answer incorrectly|choose|select|pick)\b",
        r"\bmy task is to\b",
        r"\bto fulfill this request\b",
    )
]


def detect_manipulation_leak(reply_text: str) -> bool:
    """Heuristic: True if the reply appears to reveal that the AI was told to
    answer incorrectly. Meant to be checked only when answer_incorrectly=True,
    to flag/monitor prompt leakage in stored metadata (see AIMessageMetadata.
    manipulation_leaked). Scans the full reply — unlike detect_stated_choice —
    since leaks tend to surface mid-explanation rather than in the opening line.
    """
    return any(p.search(reply_text) for p in _MANIPULATION_LEAK_PATTERNS)


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
    recent_turns: int = 3,
) -> list[dict]:
    """Return the first exchange (anchors the quiz question) plus the most recent
    turns so the model always knows what question it is helping with.

    recent_turns: how many of the latest user/assistant pairs to include after
    the first exchange. Total context is at most 1 + recent_turns pairs.

    agent_prefix: if provided (e.g. '[AGENT A]'), filters and strips per-agent
    replies so each agent only sees its own history.
    """
    if agent_prefix:
        asst_query = {
            "conversation_id": conv_id,
            "role": "assistant",
            "content": {"$elemMatch": {"$regex": f"^{re.escape(agent_prefix)}"}},
        }
    else:
        asst_query = {"conversation_id": conv_id, "role": "assistant"}

    # Fetch all assistant docs in chronological order.
    all_asst = list(messages_col.find(asst_query, sort=[("created_at", 1)]))
    if not all_asst:
        return []

    def _extract_content(doc: dict) -> str:
        content = doc["content"]
        if agent_prefix and isinstance(content, list):
            matches = [c for c in content if c.startswith(agent_prefix)]
            return matches[0][len(agent_prefix):].strip() if matches else _format_assistant(content)
        return _format_assistant(content)

    def _user_before(asst_doc: dict) -> Optional[dict]:
        return messages_col.find_one(
            {
                "conversation_id": conv_id,
                "role": "user",
                "created_at": {"$lt": asst_doc["created_at"]},
            },
            sort=[("created_at", -1)],
        )

    # Build the first exchange (contains the original quiz question).
    first_asst = all_asst[0]
    first_user = _user_before(first_asst)
    if not first_user:
        return []

    first_pair = [
        {"role": "user", "content": first_user["content"]},
        {"role": "assistant", "content": _extract_content(first_asst)},
    ]

    # Build recent exchanges (skip the first one to avoid duplication).
    recent_asst_docs = all_asst[-(recent_turns):]
    if recent_asst_docs and recent_asst_docs[0]["_id"] == first_asst["_id"]:
        recent_asst_docs = recent_asst_docs[1:]

    recent_pairs: list[dict] = []
    for asst_doc in recent_asst_docs:
        user_doc = _user_before(asst_doc)
        if not user_doc:
            continue
        recent_pairs.append({"role": "user", "content": user_doc["content"]})
        recent_pairs.append({"role": "assistant", "content": _extract_content(asst_doc)})

    return first_pair + recent_pairs


def get_conversation_history(messages_col: Collection, conv_id: str) -> list[dict]:
    """Return all raw message documents for a conversation in chronological order."""
    return list(messages_col.find(
        {"conversation_id": conv_id},
        sort=[("created_at", 1)],
    ))
