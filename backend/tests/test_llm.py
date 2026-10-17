# backend/tests/test_llm.py
"""Tests for app/core/llm.py — the shared UF LiteLLM gateway client factory,
the single source of the model id, and the served-model logger."""
from unittest.mock import MagicMock

from openai import OpenAI

from app.core.llm import (
    DEFAULT_MODEL,
    get_llm_model,
    get_sync_llm_client,
    log_served_model,
    reset_served_model_log,
)


class TestGetLlmModel:
    def test_defaults_when_env_absent(self, monkeypatch):
        monkeypatch.delenv("UF_OPENAI_API_MODEL", raising=False)
        assert get_llm_model() == "gpt-4.1"

    def test_default_is_the_shared_constant(self, monkeypatch):
        # Every call site falls back through here, so the constant and the
        # fallback must not drift apart.
        monkeypatch.delenv("UF_OPENAI_API_MODEL", raising=False)
        assert get_llm_model() == DEFAULT_MODEL

    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv("UF_OPENAI_API_MODEL", "gpt-5-mini")
        assert get_llm_model() == "gpt-5-mini"


class TestGetSyncLlmClient:
    def test_builds_openai_client_pointed_at_uf_gateway(self, monkeypatch):
        monkeypatch.setenv("UF_OPENAI_API_KEY", "k")
        monkeypatch.delenv("UF_OPENAI_BASE_URL", raising=False)
        client = get_sync_llm_client()
        assert isinstance(client, OpenAI)
        assert str(client.base_url).rstrip("/") == "https://api.ai.it.ufl.edu"

    def test_respects_custom_base_url(self, monkeypatch):
        monkeypatch.setenv("UF_OPENAI_API_KEY", "k")
        monkeypatch.setenv("UF_OPENAI_BASE_URL", "https://proxy.example/v1")
        client = get_sync_llm_client()
        assert str(client.base_url).rstrip("/") == "https://proxy.example/v1"


class TestLogServedModel:
    def test_logs_the_served_model(self, capsys):
        log_served_model("chat.stream", "gpt-4.1", "gpt-4.1")
        assert "[llm] chat.stream: gateway served 'gpt-4.1'" in capsys.readouterr().out

    def test_repeats_are_deduped(self, capsys):
        for _ in range(5):
            log_served_model("chat.stream", "gpt-4.1", "gpt-4.1")
        # Steady state must stay quiet — one line per distinct answer, not per call.
        assert capsys.readouterr().out.count("[llm]") == 1

    def test_logs_again_when_the_served_model_changes(self, capsys):
        log_served_model("chat.stream", "gpt-4.1", "gpt-4.1")
        log_served_model("chat.stream", "gpt-4.1", "gpt-4.1-fallback")
        out = capsys.readouterr().out
        assert out.count("[llm]") == 2
        assert "gpt-4.1-fallback" in out

    def test_warns_when_the_gateway_substitutes(self, capsys):
        log_served_model("chat.stream", "gpt-4.1", "gpt-4o-mini")
        out = capsys.readouterr().out
        assert "requested 'gpt-4.1'" in out
        assert "served 'gpt-4o-mini'" in out
        assert "remapped" in out

    def test_substitution_warning_is_deduped_too(self, capsys):
        log_served_model("chat.stream", "gpt-4.1", "gpt-4o-mini")
        log_served_model("chat.stream", "gpt-4.1", "gpt-4o-mini")
        assert capsys.readouterr().out.count("[llm]") == 1

    def test_each_call_site_logs_separately(self, capsys):
        log_served_model("chat.stream", "gpt-4.1", "gpt-4.1")
        log_served_model("link_health.relevance", "gpt-4.1", "gpt-4.1")
        out = capsys.readouterr().out
        assert "chat.stream" in out
        assert "link_health.relevance" in out
        assert out.count("[llm]") == 2

    def test_no_claim_of_substitution_without_a_requested_id(self, capsys):
        log_served_model("search", None, "gpt-4.1")
        out = capsys.readouterr().out
        assert "gateway served 'gpt-4.1'" in out
        assert "remapped" not in out

    def test_silent_when_the_response_carries_no_model(self, capsys):
        log_served_model("chat.stream", "gpt-4.1", None)
        assert capsys.readouterr().out == ""

    def test_silent_for_an_empty_served_model(self, capsys):
        log_served_model("chat.stream", "gpt-4.1", "")
        assert capsys.readouterr().out == ""

    def test_silent_for_a_non_string_served_model(self, capsys):
        # Mocked clients hand back a MagicMock attribute rather than a string;
        # that is not evidence of anything and must not reach the log.
        log_served_model("chat.stream", "gpt-4.1", MagicMock())
        assert capsys.readouterr().out == ""

    def test_reset_makes_the_next_call_log_again(self, capsys):
        log_served_model("chat.stream", "gpt-4.1", "gpt-4.1")
        capsys.readouterr()
        reset_served_model_log()
        log_served_model("chat.stream", "gpt-4.1", "gpt-4.1")
        assert "[llm] chat.stream" in capsys.readouterr().out
