# backend/tests/test_llm.py
"""Tests for app/core/llm.py — the shared UF LiteLLM gateway client factory."""
from openai import OpenAI

from app.core.llm import get_llm_model, get_sync_llm_client


class TestGetLlmModel:
    def test_defaults_when_env_absent(self, monkeypatch):
        monkeypatch.delenv("UF_OPENAI_API_MODEL", raising=False)
        assert get_llm_model() == "gpt-4o-mini"

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
