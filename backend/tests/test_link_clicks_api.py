# backend/tests/test_link_clicks_api.py
"""FastAPI TestClient integration tests for app.api.link_clicks."""
from unittest.mock import MagicMock

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.link_clicks import router as link_clicks_router
from app.api.auth import get_current_user


# ── Local app/fixtures (do not touch conftest.py) ────────────────────────────

@pytest.fixture
def lc_mock_col():
    return MagicMock()


@pytest.fixture
def lc_mock_db(lc_mock_col):
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=lc_mock_col)
    return db


@pytest.fixture
def lc_app(lc_mock_db, regular_user):
    app = FastAPI()
    app.include_router(link_clicks_router)
    app.state.db = lc_mock_db
    app.dependency_overrides[get_current_user] = lambda: regular_user
    return app


@pytest.fixture
def lc_client(lc_app):
    return TestClient(lc_app)


@pytest.fixture
def lc_admin_app(lc_mock_db, admin_user):
    app = FastAPI()
    app.include_router(link_clicks_router)
    app.state.db = lc_mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return app


@pytest.fixture
def lc_admin_client(lc_admin_app):
    return TestClient(lc_admin_app)


# ═══════════════════════════════════════════════════════════════════════════
# POST /links/clicks
# ═══════════════════════════════════════════════════════════════════════════

class TestRecordLinkClick:
    def test_succeeds_for_regular_user_no_admin_required(self, lc_client, lc_mock_col, regular_user):
        oid = ObjectId()
        lc_mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        resp = lc_client.post("/links/clicks", json={
            "quiz_id": "links", "question_id": "q1", "conversation_id": "conv1",
            "url": "https://example.com/article",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://example.com/article"
        assert data["user_id"] == regular_user.id

    def test_missing_url_returns_422(self, lc_client):
        resp = lc_client.post("/links/clicks", json={})
        assert resp.status_code == 422

    def test_requires_authentication(self):
        app = FastAPI()
        app.include_router(link_clicks_router)
        app.state.db = MagicMock()
        client = TestClient(app)

        resp = client.post("/links/clicks", json={"url": "https://example.com"})
        assert resp.status_code != 200


# ═══════════════════════════════════════════════════════════════════════════
# GET /links/clicks
# ═══════════════════════════════════════════════════════════════════════════

class TestGetLinkClicks:
    def test_regular_user_scoped_to_own_clicks(self, lc_client, lc_mock_col, regular_user):
        lc_mock_col.find.return_value.sort.return_value = []

        resp = lc_client.get("/links/clicks")

        assert resp.status_code == 200
        lc_mock_col.find.assert_called_once_with({"user_id": regular_user.id})

    def test_admin_sees_all_clicks(self, lc_admin_client, lc_mock_col):
        lc_mock_col.find.return_value.sort.return_value = []

        resp = lc_admin_client.get("/links/clicks")

        assert resp.status_code == 200
        lc_mock_col.find.assert_called_once_with({})
