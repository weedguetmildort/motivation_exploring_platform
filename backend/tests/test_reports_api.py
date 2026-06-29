# backend/tests/test_reports_api.py
"""FastAPI TestClient integration tests for app.api.reports."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.reports import router as reports_router
from app.api.auth import get_current_user


# ── Local app/fixtures (do not touch conftest.py) ────────────────────────────

@pytest.fixture
def rp_mock_col():
    return MagicMock()


@pytest.fixture
def rp_mock_db(rp_mock_col):
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=rp_mock_col)
    return db


@pytest.fixture
def rp_app(rp_mock_db, regular_user):
    app = FastAPI()
    app.include_router(reports_router)
    app.state.db = rp_mock_db
    app.dependency_overrides[get_current_user] = lambda: regular_user
    return app


@pytest.fixture
def rp_client(rp_app):
    return TestClient(rp_app)


@pytest.fixture
def rp_admin_app(rp_mock_db, admin_user):
    app = FastAPI()
    app.include_router(reports_router)
    app.state.db = rp_mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return app


@pytest.fixture
def rp_admin_client(rp_admin_app):
    return TestClient(rp_admin_app)


def make_report_doc(_id=None, **overrides):
    doc = {
        "_id": _id if _id is not None else ObjectId(),
        "user_id": "userid1",
        "user_email": "student@test.edu",
        "quiz_id": "base",
        "question_id": "q1",
        "category": "bug",
        "description": "The submit button did nothing.",
        "status": "open",
        "comments": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    doc.update(overrides)
    return doc


# ═══════════════════════════════════════════════════════════════════════════
# POST /reports
# ═══════════════════════════════════════════════════════════════════════════

class TestSubmitReport:
    def test_succeeds_for_regular_user(self, rp_client, rp_mock_col, regular_user):
        oid = ObjectId()
        rp_mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        resp = rp_client.post("/reports", json={
            "category": "bug", "description": "Broken choice", "quiz_id": "base", "question_id": "q1",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["user_email"] == regular_user.email
        assert data["status"] == "open"

    def test_missing_description_returns_422(self, rp_client):
        resp = rp_client.post("/reports", json={"category": "bug"})
        assert resp.status_code == 422

    def test_invalid_category_returns_422(self, rp_client):
        resp = rp_client.post("/reports", json={"category": "not-a-category", "description": "x"})
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# GET /reports
# ═══════════════════════════════════════════════════════════════════════════

class TestGetReports:
    def test_regular_user_scoped_to_own_reports(self, rp_client, rp_mock_col, regular_user):
        rp_mock_col.find.return_value.sort.return_value = []

        resp = rp_client.get("/reports")

        assert resp.status_code == 200
        rp_mock_col.find.assert_called_once_with({"user_id": regular_user.id})

    def test_admin_sees_all_reports(self, rp_admin_client, rp_mock_col):
        rp_mock_col.find.return_value.sort.return_value = []

        resp = rp_admin_client.get("/reports")

        assert resp.status_code == 200
        rp_mock_col.find.assert_called_once_with({})

    def test_status_query_param_passed_through(self, rp_client, rp_mock_col, regular_user):
        rp_mock_col.find.return_value.sort.return_value = []

        rp_client.get("/reports?status=open")

        rp_mock_col.find.assert_called_once_with({"user_id": regular_user.id, "status": "open"})


# ═══════════════════════════════════════════════════════════════════════════
# GET /reports/{report_id}
# ═══════════════════════════════════════════════════════════════════════════

class TestGetSingleReport:
    def test_owner_can_view_own_report(self, rp_client, rp_mock_col, regular_user):
        oid = ObjectId()
        rp_mock_col.find_one.return_value = make_report_doc(_id=oid, user_id=regular_user.id)

        resp = rp_client.get(f"/reports/{oid}")

        assert resp.status_code == 200

    def test_other_users_report_returns_404(self, rp_client, rp_mock_col):
        oid = ObjectId()
        # Scoped query (user_id filter) won't match someone else's report.
        rp_mock_col.find_one.return_value = None

        resp = rp_client.get(f"/reports/{oid}")

        assert resp.status_code == 404

    def test_admin_can_view_any_report(self, rp_admin_client, rp_mock_col):
        oid = ObjectId()
        rp_mock_col.find_one.return_value = make_report_doc(_id=oid, user_id="someone-else")

        resp = rp_admin_client.get(f"/reports/{oid}")

        assert resp.status_code == 200

    def test_invalid_id_returns_404(self, rp_client):
        resp = rp_client.get("/reports/not-a-real-id")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# POST /reports/{report_id}/comments
# ═══════════════════════════════════════════════════════════════════════════

class TestAddReportComment:
    def test_owner_can_comment_on_own_report(self, rp_client, rp_mock_col, regular_user):
        oid = ObjectId()
        rp_mock_col.update_one.return_value = MagicMock(matched_count=1)
        rp_mock_col.find_one.return_value = make_report_doc(_id=oid, user_id=regular_user.id)

        resp = rp_client.post(f"/reports/{oid}/comments", json={"body": "Still broken."})

        assert resp.status_code == 200

    def test_other_users_report_returns_404(self, rp_client, rp_mock_col):
        oid = ObjectId()
        rp_mock_col.update_one.return_value = MagicMock(matched_count=0)

        resp = rp_client.post(f"/reports/{oid}/comments", json={"body": "Still broken."})

        assert resp.status_code == 404

    def test_empty_body_returns_422(self, rp_client):
        oid = ObjectId()
        resp = rp_client.post(f"/reports/{oid}/comments", json={"body": ""})
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# PATCH /reports/{report_id}/status
# ═══════════════════════════════════════════════════════════════════════════

class TestPatchReportStatus:
    def test_admin_can_update_status(self, rp_admin_client, rp_mock_col):
        oid = ObjectId()
        rp_mock_col.update_one.return_value = MagicMock(matched_count=1)
        rp_mock_col.find_one.return_value = make_report_doc(_id=oid, status="resolved")

        resp = rp_admin_client.patch(f"/reports/{oid}/status", json={"status": "resolved"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"

    def test_regular_user_forbidden(self, rp_client):
        oid = ObjectId()
        resp = rp_client.patch(f"/reports/{oid}/status", json={"status": "resolved"})
        assert resp.status_code == 403

    def test_not_found_returns_404(self, rp_admin_client, rp_mock_col):
        oid = ObjectId()
        rp_mock_col.update_one.return_value = MagicMock(matched_count=0)

        resp = rp_admin_client.patch(f"/reports/{oid}/status", json={"status": "resolved"})

        assert resp.status_code == 404

    def test_invalid_status_returns_422(self, rp_admin_client):
        oid = ObjectId()
        resp = rp_admin_client.patch(f"/reports/{oid}/status", json={"status": "not-a-status"})
        assert resp.status_code == 422
