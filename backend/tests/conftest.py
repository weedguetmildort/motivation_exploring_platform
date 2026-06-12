# backend/tests/conftest.py
import os

# Modules under app.api.chat (and app.main, which imports it) construct an
# AsyncOpenAI client at import time, which raises OpenAIError if no API key
# is configured. Set a dummy key before any test module imports those
# modules so collection doesn't fail when UF_OPENAI_API_KEY isn't set.
os.environ.setdefault("UF_OPENAI_API_KEY", "test-key-for-tests")

from datetime import datetime, timezone
from unittest.mock import MagicMock
from bson import ObjectId
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.schemas.user import UserPublic, SurveyStage, AssignedVar


# ── Shared user fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def admin_user():
    return UserPublic(id="adminid1", email="admin@test.edu", is_admin=True)


@pytest.fixture
def regular_user():
    return UserPublic(id="userid1", email="student@test.edu", is_admin=False)


# ── MongoDB mock helpers ─────────────────────────────────────────────────────

@pytest.fixture
def mock_col():
    """A MagicMock that stands in for a pymongo Collection.

    Deliberately does NOT pre-set find.return_value so that tests can control
    the full mock chain (e.g. col.find.return_value.sort.return_value = [...])
    without fighting a pre-existing concrete list.
    """
    return MagicMock()


@pytest.fixture
def mock_db(mock_col):
    """A MagicMock db where any db[key] returns the same mock_col."""
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=mock_col)
    return db


# ── Test FastAPI app fixtures ────────────────────────────────────────────────

@pytest.fixture
def test_app(admin_user, mock_db):
    """Minimal FastAPI app with the real routers mounted, auth mocked to admin."""
    from app.api.knowledge_links import router as links_router
    from app.api.allowlist import router as allowlist_router
    from app.api.auth import get_current_user

    app = FastAPI()
    app.include_router(links_router)
    app.include_router(allowlist_router)

    app.state.db = mock_db
    app.state.knowledge_links = []
    app.state.allowlist_cache = set()

    app.dependency_overrides[get_current_user] = lambda: admin_user
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


@pytest.fixture
def unauthed_app(regular_user, mock_db):
    """Same test app but with a non-admin user — useful for 403 checks."""
    from app.api.knowledge_links import router as links_router
    from app.api.allowlist import router as allowlist_router
    from app.api.auth import get_current_user

    app = FastAPI()
    app.include_router(links_router)
    app.include_router(allowlist_router)

    app.state.db = mock_db
    app.state.knowledge_links = []
    app.state.allowlist_cache = set()

    app.dependency_overrides[get_current_user] = lambda: regular_user
    return app


@pytest.fixture
def unauthed_client(unauthed_app):
    return TestClient(unauthed_app)


# ── Sample document factories ────────────────────────────────────────────────

def make_link_doc(status="READY", tag="Basic Probability", _id=None, **overrides):
    doc = {
        "_id": _id if _id is not None else ObjectId(),
        "title": "Test Link",
        "url": "https://khanacademy.org/math/probability",
        "tags": [tag],
        "description": "A great resource for probability.",
        "status": status,
        "active": status == "READY",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    doc.update(overrides)
    return doc


def make_allowlist_doc(domain="khanacademy.org", added_by="admin@test.edu"):
    return {
        "_id": ObjectId(),
        "domain": domain,
        "added_by": added_by,
        "added_at": datetime.now(timezone.utc),
    }
