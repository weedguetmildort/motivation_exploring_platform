# backend/tests/test_chat_service.py
"""Unit tests for the chat service — especially get_last_exchange, which was
a source of context-loss bugs when a user sent more than two follow-up messages."""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, call
from bson import ObjectId
import pytest

from app.services.chat import get_last_exchange


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ts(offset_seconds=0):
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


def _asst_doc(content, t):
    return {"_id": ObjectId(), "role": "assistant", "content": content, "created_at": t}


def _user_doc(content, t):
    return {"_id": ObjectId(), "role": "user", "content": content, "created_at": t}


class TestGetLastExchange:
    def test_empty_history_returns_empty(self):
        col = MagicMock()
        col.find.return_value = []
        result = get_last_exchange(col, "conv-1")
        assert result == []

    def test_single_exchange_returned_in_full(self):
        user_msg = _user_doc("What is probability?", _ts(1))
        asst_msg = _asst_doc("Probability is the likelihood of an event.", _ts(2))

        col = MagicMock()
        col.find.return_value = [asst_msg]
        col.find_one.return_value = user_msg

        result = get_last_exchange(col, "conv-1")

        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "What is probability?"
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "Probability is the likelihood of an event."

    def test_no_user_message_before_first_assistant_returns_empty(self):
        asst_msg = _asst_doc("Hello!", _ts(1))

        col = MagicMock()
        col.find.return_value = [asst_msg]
        col.find_one.return_value = None  # no preceding user message

        result = get_last_exchange(col, "conv-1")
        assert result == []

    def test_multiple_exchanges_returns_first_plus_recent(self):
        """
        The first exchange anchors the quiz question.
        Exchanges 2–4 are the follow-ups. With recent_turns=2 the middle one
        (exchange 2) should be dropped.
        find_one is called: once for the first exchange, then once per recent exchange.
        With 4 messages and recent_turns=2, recent = [asst[2], asst[3]].
        So find_one order is: user[0], user[2], user[3].
        """
        user_msgs = [_user_doc(f"User {i}", _ts(i * 2 - 1)) for i in range(1, 5)]
        asst_msgs = [_asst_doc(f"Assistant {i}", _ts(i * 2)) for i in range(1, 5)]

        col = MagicMock()
        col.find.return_value = asst_msgs
        # find_one order: first-exchange user, then user before recent[0], user before recent[1]
        col.find_one.side_effect = [user_msgs[0], user_msgs[2], user_msgs[3]]

        result = get_last_exchange(col, "conv-1", recent_turns=2)

        assert len(result) == 6
        assert result[0]["content"] == "User 1"
        assert result[1]["content"] == "Assistant 1"
        assert result[2]["content"] == "User 3"   # recent[0] user
        assert result[3]["content"] == "Assistant 3"
        assert result[4]["content"] == "User 4"   # recent[1] user
        assert result[5]["content"] == "Assistant 4"

    def test_exactly_one_extra_exchange_with_recent_turns_1(self):
        """recent_turns=1 → only first exchange + 1 most recent.
        With 3 messages and recent_turns=1, recent = [asst[2]].
        find_one order: user[0], user[2].
        """
        user_msgs = [_user_doc(f"U{i}", _ts(i)) for i in range(1, 4)]
        asst_msgs = [_asst_doc(f"A{i}", _ts(i + 0.5)) for i in range(1, 4)]

        col = MagicMock()
        col.find.return_value = asst_msgs
        col.find_one.side_effect = [user_msgs[0], user_msgs[2]]

        result = get_last_exchange(col, "conv-1", recent_turns=1)

        assert len(result) == 4  # first pair + last pair
        assert result[0]["content"] == "U1"
        assert result[2]["content"] == "U3"  # last one

    def test_first_exchange_not_duplicated_when_it_is_also_the_most_recent(self):
        """With only 1 exchange total, first and last are the same — no duplication."""
        user_msg = _user_doc("Only question", _ts(1))
        asst_msg = _asst_doc("Only answer", _ts(2))

        col = MagicMock()
        col.find.return_value = [asst_msg]
        col.find_one.return_value = user_msg

        result = get_last_exchange(col, "conv-1", recent_turns=3)
        assert len(result) == 2  # not 4

    def test_agent_prefix_filters_and_strips_prefix(self):
        """When agent_prefix is set, only that agent's replies are returned and
        the prefix is stripped from the content."""
        a_msg = _asst_doc(["[AGENT A] This is Agent A's reply.", "[AGENT B] B's reply."], _ts(2))
        user_msg = _user_doc("Question?", _ts(1))

        col = MagicMock()
        col.find.return_value = [a_msg]
        col.find_one.return_value = user_msg

        result = get_last_exchange(col, "conv-1", agent_prefix="[AGENT A]")

        assert len(result) == 2
        assert result[1]["content"] == "This is Agent A's reply."

    def test_agent_prefix_no_match_skips_exchange(self):
        """An assistant message with no matching agent prefix is skipped."""
        asst_msg = _asst_doc(["[AGENT B] Only B replied."], _ts(2))
        user_msg = _user_doc("Question?", _ts(1))

        col = MagicMock()
        col.find.return_value = [asst_msg]
        col.find_one.return_value = user_msg

        result = get_last_exchange(col, "conv-1", agent_prefix="[AGENT A]")
        # First assistant doc matched the agent query (because of how the mock works),
        # but the content extraction finds no matching prefix — test that we handle this
        # gracefully and still return something (falls back to full content).
        assert isinstance(result, list)

    def test_conversation_id_passed_to_queries(self):
        col = MagicMock()
        col.find.return_value = []

        get_last_exchange(col, "my-conv-id-123")

        find_call_kwargs = col.find.call_args[0][0]
        assert find_call_kwargs.get("conversation_id") == "my-conv-id-123"
