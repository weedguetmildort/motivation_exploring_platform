# backend/app/core/llm.py
"""Central factory for the UF LiteLLM gateway client.

All server-side (non-streaming) LLM calls — link relevance, question difficulty,
etc. — build their client here so the gateway URL, API key, and default model
live in exactly one place. The gateway is an OpenAI-compatible LiteLLM proxy, so
we use the openai SDK pointed at UF_OPENAI_BASE_URL.

The streaming chat path in app/api/chat.py keeps its own module-level AsyncOpenAI
client; this factory is for the synchronous background/admin tasks.
"""
import os
from openai import OpenAI

UF_BASE_URL_DEFAULT = "https://api.ai.it.ufl.edu"
DEFAULT_MODEL = "gpt-4o-mini"


def get_llm_model() -> str:
    """The model id served by the UF LiteLLM gateway."""
    return os.getenv("UF_OPENAI_API_MODEL", DEFAULT_MODEL)


def get_sync_llm_client() -> OpenAI:
    """Build a synchronous OpenAI client pointed at the UF LiteLLM gateway."""
    return OpenAI(
        api_key=os.getenv("UF_OPENAI_API_KEY"),
        base_url=os.getenv("UF_OPENAI_BASE_URL", UF_BASE_URL_DEFAULT),
    )
