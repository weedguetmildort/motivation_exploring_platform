# backend/app/core/llm.py
"""Central factory for the UF LiteLLM gateway client.

Every server-side LLM call — the streaming chat path, link relevance, question
difficulty — resolves the gateway URL, API key and model id here, so they live
in exactly one place. The gateway is an OpenAI-compatible LiteLLM proxy, so we
use the openai SDK pointed at UF_OPENAI_BASE_URL.

The streaming chat path in app/api/chat.py keeps its own module-level AsyncOpenAI
client (it needs the async flavour); this factory is for the synchronous
background/admin tasks. Both resolve the model through get_llm_model().
"""
import os
from typing import Optional

from openai import OpenAI

UF_BASE_URL_DEFAULT = "https://api.ai.it.ufl.edu"

# Requested when UF_OPENAI_API_MODEL is unset. It has to be an id the gateway
# actually serves for the study key: GET /v1/models currently returns gpt-4.1
# and nothing else, so the previous gpt-4o-mini default would have 400'd every
# call it reached. Re-check with scripts/check_model.ps1 before changing it.
DEFAULT_MODEL = "gpt-4.1"


def get_llm_model() -> str:
    """The model id served by the UF LiteLLM gateway."""
    return os.getenv("UF_OPENAI_API_MODEL", DEFAULT_MODEL)


def get_sync_llm_client() -> OpenAI:
    """Build a synchronous OpenAI client pointed at the UF LiteLLM gateway."""
    return OpenAI(
        api_key=os.getenv("UF_OPENAI_API_KEY"),
        base_url=os.getenv("UF_OPENAI_BASE_URL", UF_BASE_URL_DEFAULT),
    )


# ── Served-model logging ─────────────────────────────────────────────────────

# Which (call site, requested, served) triples have already been printed. The
# gateway answers with the same model for every call, so logging each one would
# bury the signal; printing on first sight and again on any change means a line
# appears exactly when a retired id gets remapped underneath us.
_logged_models: set = set()


def log_served_model(call_site: str, requested: Optional[str], served) -> None:
    """Record which model the gateway actually served, once per distinct answer.

    ``served`` is the ``model`` field the gateway echoes back. Because the
    gateway is a LiteLLM proxy that is the *model group* the request routed to:
    it changes if the configured id is remapped to another group, but not if the
    same group is re-backed by a different upstream deployment. That deeper swap
    shows only in the response headers — scripts/check_model.ps1 reads those.

    A non-string ``served`` (absent on a streamed chunk, or a test double) is
    skipped rather than logged as noise.
    """
    if not isinstance(served, str) or not served:
        return
    key = (call_site, requested or "", served)
    if key in _logged_models:
        return
    _logged_models.add(key)
    if requested and served != requested:
        print(
            f"[llm] {call_site}: requested {requested!r} but the gateway served "
            f"{served!r} — the configured model id was remapped"
        )
    else:
        print(f"[llm] {call_site}: gateway served {served!r}")


def reset_served_model_log() -> None:
    """Forget what has already been logged, so the next call re-announces the
    served model. Used by tests, and after a model config change."""
    _logged_models.clear()
