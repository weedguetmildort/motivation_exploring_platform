# backend/tests/test_chat_api.py
"""Tests for app/api/chat.py: SSE chat endpoints and their helper functions.

The OpenAI client (`chat_module._client`) is patched at the
`chat.completions.create` level with fake async-iterable streams so no
network calls are made. MongoDB collections are MagicMocks.
"""
import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import bson
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat as chat_module
from app.api.auth import get_current_user
from app.schemas.user import UserPublic
from app.schemas.question import QuestionChoice


# ── Fake OpenAI streaming helpers ────────────────────────────────────────────

class _FakeChunk:
    def __init__(self, content):
        self.choices = [SimpleNamespace(delta=SimpleNamespace(content=content))]


class _FakeStream:
    """Async-iterable yielding _FakeChunk objects for the given tokens.

    __aiter__ returns a fresh generator each call so the same instance can be
    iterated independently by concurrent consumers (e.g. /chat/double).
    """

    def __init__(self, tokens):
        self._tokens = tokens

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for t in self._tokens:
            yield _FakeChunk(t)


def _mock_create(tokens):
    """AsyncMock for _client.chat.completions.create returning a fixed stream."""
    return AsyncMock(return_value=_FakeStream(tokens))


def _mock_create_sequence(token_lists):
    """AsyncMock that returns a different fake stream on each successive call."""
    return AsyncMock(side_effect=[_FakeStream(t) for t in token_lists])


def _agent_aware_create(tokens_a, tokens_b):
    """AsyncMock returning different streams based on which agent's system
    prompt is present in the outgoing messages (Agent A vs Agent B)."""
    async def _create(*args, **kwargs):
        messages = kwargs.get("messages") or []
        system = messages[0]["content"] if messages else ""
        if "Agent B" in system:
            return _FakeStream(tokens_b)
        return _FakeStream(tokens_a)
    return AsyncMock(side_effect=_create)


def _raising_create(*_a, **_k):
    raise RuntimeError("upstream boom")


def _parse_sse(body: str) -> list[dict]:
    events = []
    for chunk in body.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        assert chunk.startswith("data: ")
        events.append(json.loads(chunk[len("data: "):]))
    return events


# ── App fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def chat_col():
    col = MagicMock()
    col.find.return_value = []
    return col


@pytest.fixture
def chat_app(regular_user, chat_col):
    app = FastAPI()
    app.include_router(chat_module.router)
    app.state.messages = chat_col
    app.state.knowledge_links = []
    app.dependency_overrides[get_current_user] = lambda: regular_user
    return app


@pytest.fixture
def chat_client(chat_app):
    with TestClient(chat_app) as client:
        yield client


# ── _sse ────────────────────────────────────────────────────────────────────

class TestSse:
    def test_formats_as_server_sent_event(self):
        out = chat_module._sse({"type": "token", "content": "hi"})
        assert out == 'data: {"type": "token", "content": "hi"}\n\n'


# ── _build_system_instruction ────────────────────────────────────────────────

class TestBuildSystemInstruction:
    def test_answer_incorrectly_and_choices(self):
        text = chat_module._build_system_instruction(answer_incorrectly=True, has_choices=True)
        assert "MUST choose an incorrect answer choice" in text
        assert "Do NOT mention that your answer is intentionally incorrect" in text

    def test_answer_incorrectly_only(self):
        text = chat_module._build_system_instruction(answer_incorrectly=True, has_choices=False)
        assert "Respond confidently with an incorrect answer" in text
        assert "answer choice" not in text

    def test_choices_only(self):
        text = chat_module._build_system_instruction(answer_incorrectly=False, has_choices=True)
        assert "Choose exactly ONE of the provided answer choices" in text
        assert "incorrect" not in text

    def test_neither(self):
        text = chat_module._build_system_instruction(answer_incorrectly=False, has_choices=False)
        assert text == (
            "You are a helpful assistant who helps students answer questions. "
            "Explain your reasoning clearly."
        )

    def test_all_branches_distinct(self):
        variants = {
            chat_module._build_system_instruction(a, c)
            for a in (True, False)
            for c in (True, False)
        }
        assert len(variants) == 4


# ── _build_standard_messages ─────────────────────────────────────────────────

class TestBuildStandardMessages:
    def test_default_system_prompt(self):
        msgs = chat_module._build_standard_messages([], "hello")
        assert msgs == [
            {"role": "system", "content": chat_module._BASE_SYSTEM_PROMPT},
            {"role": "user", "content": "hello"},
        ]

    def test_includes_history_between_system_and_user(self):
        history = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ]
        msgs = chat_module._build_standard_messages(history, "q2")
        assert msgs[0]["role"] == "system"
        assert msgs[1:3] == history
        assert msgs[3] == {"role": "user", "content": "q2"}

    def test_custom_system_prompt_and_agent_name(self):
        msgs = chat_module._build_standard_messages([], "hi", system_prompt="Custom prompt", agent_name="Agent A")
        assert msgs[0]["content"] == "Custom prompt\nYou are Agent A."

    def test_agent_name_without_custom_prompt(self):
        msgs = chat_module._build_standard_messages([], "hi", agent_name="Agent B")
        assert msgs[0]["content"] == f"{chat_module._BASE_SYSTEM_PROMPT}\nYou are Agent B."


# ── _extract_metadata_from_response (dead code, but still importable) ───────

class TestExtractMetadataFromResponse:
    def test_with_usage(self):
        resp = SimpleNamespace(
            model="gpt-4",
            usage=SimpleNamespace(total_tokens=100, prompt_tokens=60, completion_tokens=40),
        )
        meta = chat_module._extract_metadata_from_response(resp)
        assert meta.model_version == "gpt-4"
        assert meta.tokens_used == 100
        assert meta.input_tokens == 60
        assert meta.output_tokens == 40
        assert meta.processing_time_ms is None

    def test_without_usage(self):
        resp = SimpleNamespace(model="gpt-4", usage=None)
        meta = chat_module._extract_metadata_from_response(resp)
        assert meta.tokens_used is None
        assert meta.input_tokens is None
        assert meta.output_tokens is None

    def test_model_version_override(self):
        resp = SimpleNamespace(model="gpt-4", usage=None)
        meta = chat_module._extract_metadata_from_response(resp, model_version="custom-version")
        assert meta.model_version == "custom-version"


# ── _save_message ─────────────────────────────────────────────────────────────

class TestSaveMessage:
    def test_inserts_doc_without_metadata(self):
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        chat_module._save_message(col, "user", user, "conv1", "hello")

        col.insert_one.assert_called_once()
        doc = col.insert_one.call_args.args[0]
        assert doc["conversation_id"] == "conv1"
        assert doc["role"] == "user"
        assert doc["user_id"] == "u1"
        assert doc["user_email"] == "a@b.com"
        assert doc["content"] == "hello"
        assert doc["source"] == "web"
        assert "metadata" not in doc

    def test_inserts_doc_with_metadata(self):
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        chat_module._save_message(col, "assistant", user, "conv1", ["hi"], metadata={"answer_incorrectly": True})

        doc = col.insert_one.call_args.args[0]
        assert doc["role"] == "assistant"
        assert doc["source"] == "ai"
        assert doc["content"] == ["hi"]
        assert doc["metadata"] == {"answer_incorrectly": True}
        # regression: stored metadata must be a plain BSON-encodable dict
        bson.encode(doc)

    def test_propagates_insert_exceptions(self):
        col = MagicMock()
        col.insert_one.side_effect = RuntimeError("db down")
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        # _save_message itself no longer swallows failures — _save_exchange is
        # responsible for catching + logging so a failure is never silent.
        with pytest.raises(RuntimeError):
            chat_module._save_message(col, "user", user, "conv1", "hello")

    def test_extra_fields_merged_into_doc(self):
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        chat_module._save_message(
            col, "user", user, "conv1", "hello",
            extra_fields={"question_id": "q1", "trigger": "followup_chip"},
        )

        doc = col.insert_one.call_args.args[0]
        assert doc["question_id"] == "q1"
        assert doc["trigger"] == "followup_chip"
        bson.encode(doc)

    def test_no_extra_fields_omits_them(self):
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        chat_module._save_message(col, "user", user, "conv1", "hello")

        doc = col.insert_one.call_args.args[0]
        assert "question_id" not in doc
        assert "trigger" not in doc


# ── _save_exchange ────────────────────────────────────────────────────────────

class TestSaveExchange:
    def test_saves_user_then_assistant(self):
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        asyncio.run(
            chat_module._save_exchange(col, user, "conv1", "hello", ["hi there"], {"answer_incorrectly": False})
        )

        assert col.insert_one.call_count == 2
        user_doc, assistant_doc = (c.args[0] for c in col.insert_one.call_args_list)
        assert user_doc["role"] == "user"
        assert user_doc["content"] == "hello"
        assert "metadata" not in user_doc
        assert assistant_doc["role"] == "assistant"
        assert assistant_doc["content"] == ["hi there"]
        assert assistant_doc["metadata"] == {"answer_incorrectly": False}
        # regression: both docs must be BSON-encodable (real pymongo would raise otherwise)
        bson.encode(user_doc)
        bson.encode(assistant_doc)

    def test_does_not_raise_when_insert_fails(self, capsys):
        col = MagicMock()
        col.insert_one.side_effect = RuntimeError("db down")
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        # A persistence failure must never propagate and break the response
        # the participant already saw stream in — but it must be loud in logs.
        asyncio.run(
            chat_module._save_exchange(col, user, "conv1", "hello", ["hi there"], None)
        )

        out = capsys.readouterr().out
        assert "FAILED to save USER message" in out
        assert "FAILED to save ASSISTANT message" in out
        assert "conv1" in out
        assert "u1" in out

    def test_assistant_save_still_attempted_when_user_save_fails(self):
        col = MagicMock()
        col.insert_one.side_effect = [RuntimeError("db down"), None]
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        asyncio.run(
            chat_module._save_exchange(col, user, "conv1", "hello", ["hi there"], None)
        )

        # Both inserts were attempted even though the first one failed.
        assert col.insert_one.call_count == 2

    def test_question_id_stored_on_both_docs_trigger_only_on_user_doc(self):
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        asyncio.run(
            chat_module._save_exchange(
                col, user, "conv1", "hello", ["hi there"], None,
                question_id="q1", trigger="followup_chip",
            )
        )

        user_doc, assistant_doc = (c.args[0] for c in col.insert_one.call_args_list)
        assert user_doc["question_id"] == "q1"
        assert user_doc["trigger"] == "followup_chip"
        assert assistant_doc["question_id"] == "q1"
        assert "trigger" not in assistant_doc

    def test_no_question_id_or_trigger_omits_both_fields(self):
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        asyncio.run(
            chat_module._save_exchange(col, user, "conv1", "hello", ["hi there"], None)
        )

        user_doc, assistant_doc = (c.args[0] for c in col.insert_one.call_args_list)
        assert "question_id" not in user_doc
        assert "trigger" not in user_doc
        assert "question_id" not in assistant_doc


# ── _stream_ai ─────────────────────────────────────────────────────────────────

class TestStreamAi:
    def test_yields_only_nonempty_deltas(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["Hello", "", None, " world"]))

        async def collect():
            return [d async for d in chat_module._stream_ai([{"role": "user", "content": "hi"}])]

        assert asyncio.run(collect()) == ["Hello", " world"]


# ── _stream_agent_tokens ────────────────────────────────────────────────────────

class TestStreamAgentTokens:
    def test_success_without_agent_tag(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["foo", "bar"]))

        async def collect():
            return [item async for item in chat_module._stream_agent_tokens([{"role": "user", "content": "hi"}])]

        results = asyncio.run(collect())
        assert results == [
            (False, "foo", chat_module._sse({"type": "token", "content": "foo"})),
            (False, "bar", chat_module._sse({"type": "token", "content": "bar"})),
        ]

    def test_success_with_agent_tag(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["foo"]))

        async def collect():
            return [item async for item in chat_module._stream_agent_tokens([{"role": "user", "content": "hi"}], agent_tag="A")]

        results = asyncio.run(collect())
        assert results == [(False, "foo", chat_module._sse({"type": "token", "content": "foo", "agent": "A"}))]

    def test_error_yields_single_error_event(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", AsyncMock(side_effect=RuntimeError("boom")))

        async def collect():
            return [item async for item in chat_module._stream_agent_tokens([{"role": "user", "content": "hi"}])]

        results = asyncio.run(collect())
        assert len(results) == 1
        is_error, delta, sse = results[0]
        assert is_error is True
        assert delta == ""
        assert sse == chat_module._sse({"type": "error", "detail": "Upstream AI request failed"})


# ── _standard_stream ─────────────────────────────────────────────────────────────

class TestStandardStream:
    def test_success_no_after_done(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["foo", "bar"]))
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        async def run():
            events = []
            async for sse in chat_module._standard_stream([{"role": "user", "content": "hi"}], col, user, "conv1", "hi"):
                events.append(sse)
            await asyncio.sleep(0.05)
            return events

        events = asyncio.run(run())
        assert events == [
            chat_module._sse({"type": "token", "content": "foo"}),
            chat_module._sse({"type": "token", "content": "bar"}),
            chat_module._sse({"type": "done", "conversation_id": "conv1"}),
        ]
        assistant_doc = col.insert_one.call_args_list[1].args[0]
        assert assistant_doc["content"] == ["foobar"]
        assert assistant_doc["metadata"] == {"answer_incorrectly": False}
        bson.encode(assistant_doc)

    def test_reply_prefix_prepended_to_stored_reply(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["foo"]))
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        async def run():
            events = []
            async for sse in chat_module._standard_stream(
                [{"role": "user", "content": "hi"}], col, user, "conv1", "hi",
                agent_tag="A", reply_prefix="[AGENT A] ", answer_incorrectly=True,
            ):
                events.append(sse)
            await asyncio.sleep(0.05)
            return events

        events = asyncio.run(run())
        assert events[0] == chat_module._sse({"type": "token", "content": "foo", "agent": "A"})
        assistant_doc = col.insert_one.call_args_list[1].args[0]
        assert assistant_doc["content"] == ["[AGENT A] foo"]
        assert assistant_doc["metadata"] == {"answer_incorrectly": True}

    def test_error_mid_stream_no_save(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", AsyncMock(side_effect=RuntimeError("boom")))
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        async def run():
            events = []
            async for sse in chat_module._standard_stream([{"role": "user", "content": "hi"}], col, user, "conv1", "hi"):
                events.append(sse)
            await asyncio.sleep(0.05)
            return events

        events = asyncio.run(run())
        assert events == [chat_module._sse({"type": "error", "detail": "Upstream AI request failed"})]
        col.insert_one.assert_not_called()

    def test_after_done_called_when_request_none(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["foo"]))
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        async def after_done(full_reply):
            yield chat_module._sse({"type": "followup", "token": f"more about {full_reply}"})

        async def run():
            events = []
            async for sse in chat_module._standard_stream(
                [{"role": "user", "content": "hi"}], col, user, "conv1", "hi", after_done=after_done,
            ):
                events.append(sse)
            return events

        events = asyncio.run(run())
        assert events[-1] == chat_module._sse({"type": "followup", "token": "more about foo"})

    def test_after_done_skipped_when_request_disconnected(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["foo"]))
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        class FakeRequest:
            async def is_disconnected(self):
                return True

        called = False

        async def after_done(full_reply):
            nonlocal called
            called = True
            yield "should-not-happen"

        async def run():
            events = []
            async for sse in chat_module._standard_stream(
                [{"role": "user", "content": "hi"}], col, user, "conv1", "hi",
                after_done=after_done, request=FakeRequest(),
            ):
                events.append(sse)
            return events

        events = asyncio.run(run())
        assert events[-1] == chat_module._sse({"type": "done", "conversation_id": "conv1"})
        assert called is False

    def test_question_id_and_trigger_passed_to_save(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["foo"]))
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        async def run():
            async for _ in chat_module._standard_stream(
                [{"role": "user", "content": "hi"}], col, user, "conv1", "hi",
                question_id="q1", trigger="manual",
            ):
                pass

        asyncio.run(run())
        user_doc, assistant_doc = (c.args[0] for c in col.insert_one.call_args_list)
        assert user_doc["question_id"] == "q1"
        assert user_doc["trigger"] == "manual"
        assert assistant_doc["question_id"] == "q1"

    def test_stated_choice_detected_with_answer_choices(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["The answer is 4."]))
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)
        choices = [QuestionChoice(id="a", label="3"), QuestionChoice(id="b", label="4")]

        async def run():
            async for _ in chat_module._standard_stream(
                [{"role": "user", "content": "hi"}], col, user, "conv1", "hi",
                answer_choices=choices,
            ):
                pass

        asyncio.run(run())
        assistant_doc = col.insert_one.call_args_list[1].args[0]
        assert assistant_doc["metadata"]["stated_choice_id"] == {"default": "b"}

    def test_no_stated_choice_field_without_answer_choices(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["The answer is 4."]))
        col = MagicMock()
        user = UserPublic(id="u1", email="a@b.com", is_admin=False)

        async def run():
            async for _ in chat_module._standard_stream(
                [{"role": "user", "content": "hi"}], col, user, "conv1", "hi",
            ):
                pass

        asyncio.run(run())
        assistant_doc = col.insert_one.call_args_list[1].args[0]
        assert "stated_choice_id" not in assistant_doc.get("metadata", {})


# ── _stream_into_queue ───────────────────────────────────────────────────────────

class TestStreamIntoQueue:
    def test_success_puts_token_items_then_returns(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["foo", "bar"]))

        async def run():
            queue: asyncio.Queue = asyncio.Queue()
            await chat_module._stream_into_queue([{"role": "user", "content": "hi"}], "A", queue)
            items = []
            while not queue.empty():
                items.append(queue.get_nowait())
            return items

        items = asyncio.run(run())
        assert items == [
            (False, "foo", "A", chat_module._sse({"type": "token", "content": "foo", "agent": "A"})),
            (False, "bar", "A", chat_module._sse({"type": "token", "content": "bar", "agent": "A"})),
        ]

    def test_error_puts_single_error_item(self, monkeypatch):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", AsyncMock(side_effect=RuntimeError("boom")))

        async def run():
            queue: asyncio.Queue = asyncio.Queue()
            await chat_module._stream_into_queue([{"role": "user", "content": "hi"}], "B", queue)
            return queue.get_nowait()

        is_error, delta, tag, sse = asyncio.run(run())
        assert is_error is True
        assert delta == ""
        assert tag == "B"
        assert sse == chat_module._sse({"type": "error", "detail": "Upstream AI request failed"})

    def test_cancelled_error_is_caught(self, monkeypatch):
        async def _slow_create(*_a, **_k):
            await asyncio.sleep(10)

        monkeypatch.setattr(chat_module._client.chat.completions, "create", AsyncMock(side_effect=_slow_create))

        async def run():
            queue: asyncio.Queue = asyncio.Queue()
            task = asyncio.create_task(chat_module._stream_into_queue([{"role": "user", "content": "hi"}], "A", queue))
            await asyncio.sleep(0.01)
            task.cancel()
            await task

        # should not raise
        asyncio.run(run())


# ── POST /chat/{quiz_id} (default) ────────────────────────────────────────────

class TestDefaultChatEndpoint:
    def test_missing_api_key_returns_500(self, monkeypatch, chat_client):
        monkeypatch.setattr(chat_module, "_UF_API_KEY", "")
        resp = chat_client.post("/chat/quiz1", json={"message": "hi"})
        assert resp.status_code == 500
        assert "UF_OPENAI_API_KEY" in resp.json()["detail"]

    def test_streams_tokens_and_done(self, monkeypatch, chat_client, chat_col):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["Hello", " world"]))

        resp = chat_client.post("/chat/quiz1", json={"message": "hi", "conversation_id": "conv1"})

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert events[0] == {"type": "token", "content": "Hello"}
        assert events[1] == {"type": "token", "content": " world"}
        assert events[2] == {"type": "done", "conversation_id": "conv1"}

    def test_generates_conversation_id_when_absent(self, monkeypatch, chat_client):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["hi"]))

        resp = chat_client.post("/chat/quiz1", json={"message": "hi"})

        events = _parse_sse(resp.text)
        done = events[-1]
        assert done["type"] == "done"
        assert done["conversation_id"]  # non-empty generated uuid

    def test_answer_incorrectly_with_choices_uses_choice_system_prompt(self, monkeypatch, chat_client):
        create_mock = _mock_create(["ok"])
        monkeypatch.setattr(chat_module._client.chat.completions, "create", create_mock)

        resp = chat_client.post("/chat/quiz1", json={
            "message": "What is 2+2?",
            "answer_incorrectly": True,
            "answer_choices": [{"id": "a", "label": "3"}, {"id": "b", "label": "4"}],
        })

        assert resp.status_code == 200
        sent_messages = create_mock.call_args.kwargs["messages"]
        assert "MUST choose an incorrect answer choice" in sent_messages[0]["content"]

    def test_question_id_and_trigger_round_trip_to_stored_docs(self, monkeypatch, chat_client, chat_col):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["hi"]))

        resp = chat_client.post("/chat/quiz1", json={
            "message": "hi", "conversation_id": "conv1",
            "question_id": "q42", "trigger": "auto_question",
        })

        assert resp.status_code == 200
        user_doc, assistant_doc = (c.args[0] for c in chat_col.insert_one.call_args_list)
        assert user_doc["question_id"] == "q42"
        assert user_doc["trigger"] == "auto_question"
        assert assistant_doc["question_id"] == "q42"

    def test_stated_choice_id_round_trips_to_stored_metadata(self, monkeypatch, chat_client, chat_col):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["The answer is 4."]))

        resp = chat_client.post("/chat/quiz1", json={
            "message": "What is 2+2?",
            "answer_choices": [{"id": "a", "label": "3"}, {"id": "b", "label": "4"}],
        })

        assert resp.status_code == 200
        assistant_doc = chat_col.insert_one.call_args_list[1].args[0]
        assert assistant_doc["metadata"]["stated_choice_id"] == {"default": "b"}


# ── POST /chat/double ──────────────────────────────────────────────────────────

class TestDoubleChatEndpoint:
    def test_missing_api_key_returns_500(self, monkeypatch, chat_client):
        monkeypatch.setattr(chat_module, "_UF_API_KEY", "")
        resp = chat_client.post("/chat/double", json={"message": "hi"})
        assert resp.status_code == 500
        assert "UF_OPENAI_API_KEY" in resp.json()["detail"]

    def test_both_agents_run_by_default(self, monkeypatch, chat_client, chat_col):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _agent_aware_create(["A says hi"], ["B says hi"]))

        resp = chat_client.post("/chat/double", json={"message": "hi", "conversation_id": "conv1", "agents": []})

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        token_events = [e for e in events if e["type"] == "token"]
        agents_seen = {e["agent"] for e in token_events}
        assert agents_seen == {"A", "B"}
        assert events[-1] == {"type": "done", "conversation_id": "conv1"}

    def test_invalid_agent_falls_back_to_both(self, monkeypatch, chat_client, chat_col):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _agent_aware_create(["A reply"], ["B reply"]))

        resp = chat_client.post("/chat/double", json={"message": "hi", "conversation_id": "conv1", "agents": ["not-a-real-agent"]})

        events = _parse_sse(resp.text)
        agents_seen = {e["agent"] for e in events if e["type"] == "token"}
        assert agents_seen == {"A", "B"}

    def test_single_agent_via_mention(self, monkeypatch, chat_client, chat_col):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _agent_aware_create(["solo reply"], ["should not run"]))

        resp = chat_client.post("/chat/double", json={"message": "hi", "conversation_id": "conv1", "agents": ["AgentA"]})

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        token_events = [e for e in events if e["type"] == "token"]
        assert all(e["agent"] == "A" for e in token_events)
        assert "".join(e["content"] for e in token_events) == "solo reply"
        assert events[-1] == {"type": "done", "conversation_id": "conv1"}

        assert chat_col.insert_one.call_count == 2
        assistant_doc = chat_col.insert_one.call_args_list[1].args[0]
        assert assistant_doc["content"] == ["[AGENT A] solo reply"]

    def test_both_agents_stores_combined_replies(self, monkeypatch, chat_client, chat_col):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _agent_aware_create(["hello-a"], ["hello-b"]))

        resp = chat_client.post("/chat/double", json={"message": "hi", "conversation_id": "conv1", "agents": []})

        assert resp.status_code == 200
        assert chat_col.insert_one.call_count == 2
        assistant_doc = chat_col.insert_one.call_args_list[1].args[0]
        assert set(assistant_doc["content"]) == {"[AGENT A] hello-a", "[AGENT B] hello-b"}
        assert assistant_doc["metadata"] == {"answer_incorrectly": False}
        bson.encode(assistant_doc)

    def test_both_agents_stated_choice_detected_per_agent(self, monkeypatch, chat_client, chat_col):
        monkeypatch.setattr(
            chat_module._client.chat.completions, "create",
            _agent_aware_create(["The answer is 3, intuitively."], ["The answer is 4, formally."]),
        )

        resp = chat_client.post("/chat/double", json={
            "message": "hi", "conversation_id": "conv1", "agents": [],
            "answer_choices": [{"id": "a", "label": "3"}, {"id": "b", "label": "4"}],
        })

        assert resp.status_code == 200
        assistant_doc = chat_col.insert_one.call_args_list[1].args[0]
        assert assistant_doc["metadata"]["stated_choice_id"] == {"A": "a", "B": "b"}

    def test_question_id_and_trigger_round_trip_both_agents(self, monkeypatch, chat_client, chat_col):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _agent_aware_create(["a"], ["b"]))

        resp = chat_client.post("/chat/double", json={
            "message": "hi", "conversation_id": "conv1", "agents": [],
            "question_id": "q7", "trigger": "manual",
        })

        assert resp.status_code == 200
        user_doc, assistant_doc = (c.args[0] for c in chat_col.insert_one.call_args_list)
        assert user_doc["question_id"] == "q7"
        assert user_doc["trigger"] == "manual"
        assert assistant_doc["question_id"] == "q7"

    def test_single_agent_via_mention_question_id_round_trips(self, monkeypatch, chat_client, chat_col):
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _agent_aware_create(["solo"], ["unused"]))

        resp = chat_client.post("/chat/double", json={
            "message": "hi", "conversation_id": "conv1", "agents": ["AgentA"],
            "question_id": "q9", "trigger": "followup_chip",
        })

        assert resp.status_code == 200
        user_doc, assistant_doc = (c.args[0] for c in chat_col.insert_one.call_args_list)
        assert user_doc["question_id"] == "q9"
        assert user_doc["trigger"] == "followup_chip"
        assert assistant_doc["question_id"] == "q9"


# ── POST /chat/followup ─────────────────────────────────────────────────────────

class TestFollowupChatEndpoint:
    def test_missing_api_key_returns_500(self, monkeypatch, chat_client):
        monkeypatch.setattr(chat_module, "_UF_API_KEY", "")
        resp = chat_client.post("/chat/followup", json={"message": "hi"})
        assert resp.status_code == 500
        assert "UF_OPENAI_API_KEY" in resp.json()["detail"]

    def test_streams_answer_then_followup_questions(self, monkeypatch, chat_client, chat_col):
        monkeypatch.setattr(
            chat_module._client.chat.completions, "create",
            _mock_create_sequence([["main answer"], ["1. Q1\n2. Q2\n3. Q3"]]),
        )

        resp = chat_client.post("/chat/followup", json={"message": "explain", "conversation_id": "conv2"})

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert events[0] == {"type": "token", "content": "main answer"}
        assert events[1] == {"type": "done", "conversation_id": "conv2"}
        followups = [e for e in events if e["type"] == "followup"]
        assert followups == [{"type": "followup", "token": "1. Q1\n2. Q2\n3. Q3"}]

    def test_question_id_and_trigger_round_trip(self, monkeypatch, chat_client, chat_col):
        monkeypatch.setattr(
            chat_module._client.chat.completions, "create",
            _mock_create_sequence([["main answer"], ["1. Q1"]]),
        )

        resp = chat_client.post("/chat/followup", json={
            "message": "explain", "conversation_id": "conv2",
            "question_id": "q5", "trigger": "manual",
        })

        assert resp.status_code == 200
        user_doc, assistant_doc = (c.args[0] for c in chat_col.insert_one.call_args_list)
        assert user_doc["question_id"] == "q5"
        assert user_doc["trigger"] == "manual"
        assert assistant_doc["question_id"] == "q5"


# ── POST /chat/links ──────────────────────────────────────────────────────────

class TestLinksChatEndpoint:
    def test_missing_api_key_returns_500(self, monkeypatch, chat_client):
        monkeypatch.setattr(chat_module, "_UF_API_KEY", "")
        resp = chat_client.post("/chat/links", json={"message": "hi"})
        assert resp.status_code == 500
        assert "UF_OPENAI_API_KEY" in resp.json()["detail"]

    def test_no_knowledge_links_no_citations(self, monkeypatch, chat_client, chat_app, chat_col):
        chat_app.state.knowledge_links = []
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["plain answer"]))

        resp = chat_client.post("/chat/links", json={"message": "hi", "conversation_id": "conv3"})

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert all(e["type"] != "citations" for e in events)
        done = events[-1]
        assert done == {"type": "done", "conversation_id": "conv3", "reply": "plain answer"}

    def test_knowledge_links_emit_citations_and_inject_links(self, monkeypatch, chat_client, chat_app, chat_col):
        chat_app.state.knowledge_links = [
            {"title": "Probability Basics", "url": "https://khanacademy.org/prob", "description": "Intro to probability", "tags": ["Basic Probability"]},
        ]
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["The answer is ", "[1]", "."]))

        resp = chat_client.post("/chat/links", json={"message": "hi", "conversation_id": "conv4"})

        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert events[0] == {"type": "citations", "citations": [{"n": 1, "title": "Probability Basics", "url": "https://khanacademy.org/prob"}]}
        done = events[-1]
        assert done["type"] == "done"
        assert done["conversation_id"] == "conv4"
        assert "https://khanacademy.org/prob" in done["reply"]

        assert chat_col.insert_one.call_count == 2
        assistant_doc = chat_col.insert_one.call_args_list[1].args[0]
        assert "https://khanacademy.org/prob" in assistant_doc["content"][0]

    def test_knowledge_links_without_url_are_ignored(self, monkeypatch, chat_client, chat_app, chat_col):
        chat_app.state.knowledge_links = [{"title": "No URL here", "description": "missing url"}]
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["plain answer"]))

        resp = chat_client.post("/chat/links", json={"message": "hi", "conversation_id": "conv5"})

        events = _parse_sse(resp.text)
        assert all(e["type"] != "citations" for e in events)

    def test_error_during_streaming_returns_error_event_only(self, monkeypatch, chat_client, chat_app, chat_col):
        chat_app.state.knowledge_links = []
        monkeypatch.setattr(chat_module._client.chat.completions, "create", AsyncMock(side_effect=RuntimeError("boom")))

        resp = chat_client.post("/chat/links", json={"message": "hi", "conversation_id": "conv6"})

        events = _parse_sse(resp.text)
        assert events == [{"type": "error", "detail": "Upstream AI request failed"}]
        chat_col.insert_one.assert_not_called()

    def test_question_id_and_trigger_round_trip(self, monkeypatch, chat_client, chat_app, chat_col):
        chat_app.state.knowledge_links = []
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["plain answer"]))

        resp = chat_client.post("/chat/links", json={
            "message": "hi", "conversation_id": "conv3",
            "question_id": "q11", "trigger": "manual",
        })

        assert resp.status_code == 200
        user_doc, assistant_doc = (c.args[0] for c in chat_col.insert_one.call_args_list)
        assert user_doc["question_id"] == "q11"
        assert user_doc["trigger"] == "manual"
        assert assistant_doc["question_id"] == "q11"

    def test_stated_choice_id_detected(self, monkeypatch, chat_client, chat_app, chat_col):
        chat_app.state.knowledge_links = []
        monkeypatch.setattr(chat_module._client.chat.completions, "create", _mock_create(["The answer is 4."]))

        resp = chat_client.post("/chat/links", json={
            "message": "What is 2+2?", "conversation_id": "conv3",
            "answer_choices": [{"id": "a", "label": "3"}, {"id": "b", "label": "4"}],
        })

        assert resp.status_code == 200
        assistant_doc = chat_col.insert_one.call_args_list[1].args[0]
        assert assistant_doc["metadata"]["stated_choice_id"] == {"default": "b"}


# ── GET /chat/get_history/{conversation_id} ───────────────────────────────────

class TestGetConversationHistory:
    def test_empty_history_returns_empty_messages(self, chat_client, chat_col):
        chat_col.find.return_value = []
        resp = chat_client.get("/chat/get_history/conv1")
        assert resp.status_code == 200
        assert resp.json() == {"conversation_id": "conv1", "messages": []}

    def test_other_users_conversation_is_forbidden(self, chat_client, chat_col):
        chat_col.find.return_value = [
            {"user_id": "someone-else", "role": "user", "content": "hi", "created_at": datetime.now(timezone.utc)},
        ]
        resp = chat_client.get("/chat/get_history/conv1")
        assert resp.status_code == 403

    def test_metadata_dict_without_agents_key(self, chat_client, chat_col, regular_user):
        now = datetime.now(timezone.utc)
        chat_col.find.return_value = [
            {"user_id": regular_user.id, "role": "user", "content": "hi", "created_at": now, "user_email": regular_user.email},
            {
                "user_id": regular_user.id, "role": "assistant", "content": ["hi there"], "created_at": now,
                "user_email": regular_user.email, "metadata": {"answer_incorrectly": True},
            },
        ]
        resp = chat_client.get("/chat/get_history/conv1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["messages"][0]["metadata"] is None
        assert body["messages"][1]["metadata"]["answer_incorrectly"] is True

    def test_metadata_dict_with_agents_key(self, chat_client, chat_col, regular_user):
        now = datetime.now(timezone.utc)
        chat_col.find.return_value = [
            {"user_id": regular_user.id, "role": "user", "content": "hi", "created_at": now, "user_email": regular_user.email},
            {
                "user_id": regular_user.id, "role": "assistant", "content": ["[AGENT A] a", "[AGENT B] b"], "created_at": now,
                "user_email": regular_user.email, "metadata": {"agents": ["A", "B"]},
            },
        ]
        resp = chat_client.get("/chat/get_history/conv1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["messages"][1]["metadata"]["custom_metadata"] == {"agents": ["A", "B"]}

    def test_invalid_metadata_is_swallowed_to_none(self, chat_client, chat_col, regular_user):
        now = datetime.now(timezone.utc)
        chat_col.find.return_value = [
            {"user_id": regular_user.id, "role": "user", "content": "hi", "created_at": now, "user_email": regular_user.email},
            {
                "user_id": regular_user.id, "role": "assistant", "content": ["bad"], "created_at": now,
                "user_email": regular_user.email, "metadata": {"tokens_used": "not-a-number"},
            },
        ]
        resp = chat_client.get("/chat/get_history/conv1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["messages"][1]["metadata"] is None

    def test_unexpected_exception_returns_500(self, chat_client, chat_col):
        chat_col.find.side_effect = RuntimeError("db exploded")
        resp = chat_client.get("/chat/get_history/conv1")
        assert resp.status_code == 500
        assert "Failed to retrieve conversation" in resp.json()["detail"]


# ── GET /chat/load_user_history/{conversation_id} ─────────────────────────────

class TestLoadUserHistory:
    def test_empty_history_returns_empty_messages(self, chat_client, chat_col):
        chat_col.find.return_value = []
        resp = chat_client.get("/chat/load_user_history/conv1")
        assert resp.status_code == 200
        assert resp.json() == {"conversation_id": "conv1", "messages": []}

    def test_other_users_conversation_is_forbidden(self, chat_client, chat_col):
        chat_col.find.return_value = [
            {"user_id": "someone-else", "role": "user", "content": "hi", "created_at": datetime.now(timezone.utc)},
        ]
        resp = chat_client.get("/chat/load_user_history/conv1")
        assert resp.status_code == 403

    def test_returns_last_5_user_and_assistant_messages_sorted(self, chat_client, chat_col, regular_user):
        docs = []
        for i in range(7):
            ts = datetime(2024, 1, 1, tzinfo=timezone.utc).replace(minute=i * 2)
            docs.append({"user_id": regular_user.id, "role": "user", "content": f"q{i}", "created_at": ts})
            ts2 = ts.replace(minute=i * 2 + 1)
            docs.append({"user_id": regular_user.id, "role": "assistant", "content": [f"a{i}"], "created_at": ts2})
        chat_col.find.return_value = docs

        resp = chat_client.get("/chat/load_user_history/conv1")

        assert resp.status_code == 200
        body = resp.json()
        # last 5 user + last 5 assistant = 10 messages, sorted chronologically
        assert len(body["messages"]) == 10
        contents = [m["content"] for m in body["messages"]]
        assert contents[0] == "q2"
        assert contents[1] == ["a2"]
        assert contents[-1] == ["a6"]
        roles = [m["role"] for m in body["messages"]]
        assert roles.count("user") == 5
        assert roles.count("assistant") == 5
