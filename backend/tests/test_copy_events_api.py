# backend/tests/test_copy_events_api.py
"""FastAPI TestClient integration tests for app.api.copy_events."""
from unittest.mock import MagicMock

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.copy_events import router as copy_events_router
from app.api.auth import get_current_user


# ── Local app/fixtures (do not touch conftest.py) ────────────────────────────

@pytest.fixture
def ce_mock_col():
    return MagicMock()


@pytest.fixture
def ce_mock_db(ce_mock_col):
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=ce_mock_col)
    return db


@pytest.fixture
def ce_app(ce_mock_db, regular_user):
    app = FastAPI()
    app.include_router(copy_events_router)
    app.state.db = ce_mock_db
    app.dependency_overrides[get_current_user] = lambda: regular_user
    return app


@pytest.fixture
def ce_client(ce_app):
    return TestClient(ce_app)


@pytest.fixture
def ce_admin_app(ce_mock_db, admin_user):
    app = FastAPI()
    app.include_router(copy_events_router)
    app.state.db = ce_mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return app


@pytest.fixture
def ce_admin_client(ce_admin_app):
    return TestClient(ce_admin_app)


# ═══════════════════════════════════════════════════════════════════════════
# POST /copy-events
# ═══════════════════════════════════════════════════════════════════════════

class TestRecordCopyEvent:
    def test_succeeds_for_regular_user_no_admin_required(self, ce_client, ce_mock_col, regular_user):
        oid = ObjectId()
        ce_mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        resp = ce_client.post("/copy-events", json={
            "quiz_id": "base", "question_id": "q1", "conversation_id": "conv1",
            "copied_text": "The answer is 4.",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["copied_text"] == "The answer is 4."
        assert data["user_id"] == regular_user.id

    def test_missing_copied_text_returns_422(self, ce_client):
        resp = ce_client.post("/copy-events", json={})
        assert resp.status_code == 422

    def test_empty_copied_text_returns_422(self, ce_client):
        resp = ce_client.post("/copy-events", json={"copied_text": ""})
        assert resp.status_code == 422

    def test_overlong_copied_text_returns_422(self, ce_client):
        resp = ce_client.post("/copy-events", json={"copied_text": "x" * 2001})
        assert resp.status_code == 422

    def test_requires_authentication(self):
        app = FastAPI()
        app.include_router(copy_events_router)
        app.state.db = MagicMock()
        client = TestClient(app)

        resp = client.post("/copy-events", json={"copied_text": "hi"})
        assert resp.status_code != 200


# ═══════════════════════════════════════════════════════════════════════════
# GET /copy-events
# ═══════════════════════════════════════════════════════════════════════════

class TestGetCopyEvents:
    def test_regular_user_scoped_to_own_events(self, ce_client, ce_mock_col, regular_user):
        ce_mock_col.find.return_value.sort.return_value = []

        resp = ce_client.get("/copy-events")

        assert resp.status_code == 200
        ce_mock_col.find.assert_called_once_with({"user_id": regular_user.id})

    def test_admin_sees_all_events(self, ce_admin_client, ce_mock_col):
        ce_mock_col.find.return_value.sort.return_value = []

        resp = ce_admin_client.get("/copy-events")

        assert resp.status_code == 200
        ce_mock_col.find.assert_called_once_with({})
