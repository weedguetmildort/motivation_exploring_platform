# backend/tests/test_api.py
"""API integration tests for the knowledge-links and allowlist routes.

These tests exercise the full HTTP layer (routing, auth enforcement, response
shape, in-memory cache updates) while mocking out MongoDB at the collection
level so no real database is needed.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from bson import ObjectId
import pytest

from tests.conftest import make_link_doc, make_allowlist_doc


# ═══════════════════════════════════════════════════════════════════════════════
# Knowledge-Links API
# ═══════════════════════════════════════════════════════════════════════════════

class TestKnowledgeLinksAuth:
    """Non-admin users must be blocked from every link endpoint."""

    def test_get_links_requires_admin(self, unauthed_client):
        resp = unauthed_client.get("/knowledge-links")
        assert resp.status_code == 403

    def test_create_link_requires_admin(self, unauthed_client):
        resp = unauthed_client.post("/knowledge-links", json={
            "title": "T", "url": "https://example.com", "description": "D", "tags": ["Other"],
        })
        assert resp.status_code == 403

    def test_approve_requires_admin(self, unauthed_client):
        resp = unauthed_client.post(f"/knowledge-links/{ObjectId()}/approve")
        assert resp.status_code == 403

    def test_reject_requires_admin(self, unauthed_client):
        resp = unauthed_client.post(f"/knowledge-links/{ObjectId()}/reject")
        assert resp.status_code == 403


class TestGetKnowledgeLinks:
    def test_returns_list_of_links(self, client, mock_col):
        doc = make_link_doc(status="READY")
        mock_col.find.return_value.sort.return_value = [doc]

        resp = client.get("/knowledge-links")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == doc["title"]
        assert data[0]["status"] == "READY"

    def test_status_filter_passed_to_query(self, client, mock_col):
        mock_col.find.return_value.sort.return_value = []

        resp = client.get("/knowledge-links?status=NEEDS_REVIEW")

        assert resp.status_code == 200
        # The find call should filter by status
        mock_col.find.assert_called_with({"status": "NEEDS_REVIEW"})

    def test_empty_database_returns_empty_list(self, client, mock_col):
        mock_col.find.return_value.sort.return_value = []
        resp = client.get("/knowledge-links")
        assert resp.status_code == 200
        assert resp.json() == []


class TestCreateKnowledgeLink:
    def test_creates_link_successfully(self, client, test_app, mock_col):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        resp = client.post("/knowledge-links", json={
            "title": "Khan Academy Probability",
            "url": "https://khanacademy.org/math/probability",
            "description": "Intro to probability concepts.",
            "tags": ["Basic Probability"],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Khan Academy Probability"
        assert data["status"] == "READY"
        assert data["tags"] == ["Basic Probability"]

    def test_new_ready_link_added_to_state_cache(self, client, test_app, mock_col):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        client.post("/knowledge-links", json={
            "title": "Khan Probability",
            "url": "https://khanacademy.org/prob",
            "description": "Good resource.",
            "tags": ["Basic Probability"],
        })

        # READY link must be in the chatbot cache immediately
        cached_ids = [l["id"] for l in test_app.state.knowledge_links]
        assert str(oid) in cached_ids

    def test_missing_title_returns_422(self, client):
        resp = client.post("/knowledge-links", json={
            "url": "https://example.com",
            "description": "D",
            "tags": ["Other"],
        })
        assert resp.status_code == 422

    def test_invalid_url_returns_422(self, client):
        resp = client.post("/knowledge-links", json={
            "title": "T",
            "url": "not-a-url",
            "description": "D",
            "tags": ["Other"],
        })
        assert resp.status_code == 422


class TestApproveLink:
    def test_approve_needs_review_link(self, client, test_app, mock_col):
        oid = ObjectId()
        needs_review = make_link_doc(status="NEEDS_REVIEW", _id=oid)
        ready = make_link_doc(status="READY", _id=oid)
        mock_col.find_one.side_effect = [needs_review, ready]

        resp = client.post(f"/knowledge-links/{oid}/approve")

        assert resp.status_code == 200
        assert resp.json()["status"] == "READY"

    def test_approve_adds_link_to_cache(self, client, test_app, mock_col):
        oid = ObjectId()
        needs_review = make_link_doc(status="NEEDS_REVIEW", _id=oid)
        ready = make_link_doc(status="READY", _id=oid)
        mock_col.find_one.side_effect = [needs_review, ready]

        client.post(f"/knowledge-links/{oid}/approve")

        cached_ids = [l["id"] for l in test_app.state.knowledge_links]
        assert str(oid) in cached_ids

    def test_approve_not_found_returns_404(self, client, mock_col):
        mock_col.find_one.return_value = None

        resp = client.post(f"/knowledge-links/{ObjectId()}/approve")
        assert resp.status_code == 404


class TestRejectLink:
    def test_reject_needs_review_link(self, client, mock_col):
        oid = ObjectId()
        doc = make_link_doc(status="NEEDS_REVIEW", _id=oid)
        rejected = make_link_doc(status="REJECTED", _id=oid)
        mock_col.find_one.side_effect = [doc, rejected]

        resp = client.post(f"/knowledge-links/{oid}/reject")

        assert resp.status_code == 200
        assert resp.json()["status"] == "REJECTED"

    def test_reject_removes_link_from_cache(self, client, test_app, mock_col):
        oid = ObjectId()
        # Pre-populate cache as if the link was previously READY
        test_app.state.knowledge_links = [{"id": str(oid), "title": "T", "url": "u", "description": "d"}]

        doc = make_link_doc(status="NEEDS_REVIEW", _id=oid)
        rejected = make_link_doc(status="REJECTED", _id=oid)
        mock_col.find_one.side_effect = [doc, rejected]

        client.post(f"/knowledge-links/{oid}/reject")

        cached_ids = [l["id"] for l in test_app.state.knowledge_links]
        assert str(oid) not in cached_ids

    def test_reject_not_found_returns_404(self, client, mock_col):
        mock_col.find_one.return_value = None
        resp = client.post(f"/knowledge-links/{ObjectId()}/reject")
        assert resp.status_code == 404


class TestDeleteLink:
    def test_delete_removes_from_database_and_cache(self, client, test_app, mock_col):
        oid = ObjectId()
        doc = make_link_doc(status="READY", _id=oid)
        mock_col.find_one.return_value = doc
        test_app.state.knowledge_links = [{"id": str(oid), "title": "T", "url": "u", "description": "d"}]

        resp = client.delete(f"/knowledge-links/{oid}")

        assert resp.status_code == 200
        mock_col.delete_one.assert_called_once()
        assert all(l["id"] != str(oid) for l in test_app.state.knowledge_links)

    def test_delete_not_found_returns_404(self, client, mock_col):
        mock_col.find_one.return_value = None
        resp = client.delete(f"/knowledge-links/{ObjectId()}")
        assert resp.status_code == 404


class TestTriggerHealthCheck:
    def test_trigger_returns_ok(self, client):
        with patch("app.api.knowledge_links.threading.Thread") as MockThread:
            MockThread.return_value.start = MagicMock()
            resp = client.post("/knowledge-links/trigger-health-check")

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        MockThread.return_value.start.assert_called_once()

    def test_trigger_is_literal_path_not_caught_by_link_id_route(self, client, mock_col):
        """Ensure /trigger-health-check is not treated as a link_id."""
        with patch("app.api.knowledge_links.threading.Thread") as MockThread:
            MockThread.return_value.start = MagicMock()
            resp = client.post("/knowledge-links/trigger-health-check")

        # Must NOT call find_one (which would happen if treated as /{link_id}/...)
        mock_col.find_one.assert_not_called()
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# Allowlist API
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllowlistAuth:
    def test_get_allowlist_requires_admin(self, unauthed_client):
        resp = unauthed_client.get("/allowlist")
        assert resp.status_code == 403

    def test_add_domain_requires_admin(self, unauthed_client):
        resp = unauthed_client.post("/allowlist", json={"domain": "example.com"})
        assert resp.status_code == 403

    def test_delete_domain_requires_admin(self, unauthed_client):
        resp = unauthed_client.delete(f"/allowlist/{ObjectId()}")
        assert resp.status_code == 403


class TestGetAllowlist:
    def test_returns_list_of_entries(self, client, mock_col):
        doc = make_allowlist_doc()
        mock_col.find.return_value.sort.return_value = [doc]

        resp = client.get("/allowlist")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["domain"] == doc["domain"]

    def test_empty_allowlist_returns_empty_list(self, client, mock_col):
        mock_col.find.return_value.sort.return_value = []
        resp = client.get("/allowlist")
        assert resp.status_code == 200
        assert resp.json() == []


class TestAddAllowlistDomain:
    def test_adds_valid_domain(self, client, test_app, mock_col):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        resp = client.post("/allowlist", json={"domain": "khanacademy.org"})

        assert resp.status_code == 201
        data = resp.json()
        assert data["domain"] == "khanacademy.org"
        assert data["added_by"] == "admin@test.edu"

    def test_strips_scheme_and_path(self, client, mock_col):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        resp = client.post("/allowlist", json={"domain": "https://www.stanford.edu/courses/intro"})

        assert resp.status_code == 201
        assert resp.json()["domain"] == "stanford.edu"

    def test_adds_domain_to_state_cache(self, client, test_app, mock_col):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        client.post("/allowlist", json={"domain": "khanacademy.org"})

        assert "khanacademy.org" in test_app.state.allowlist_cache

    def test_duplicate_returns_409(self, client, mock_col):
        from pymongo.errors import DuplicateKeyError
        mock_col.insert_one.side_effect = DuplicateKeyError("dup key")

        resp = client.post("/allowlist", json={"domain": "khanacademy.org"})
        assert resp.status_code == 409

    def test_invalid_domain_format_returns_400(self, client):
        resp = client.post("/allowlist", json={"domain": "not a domain!!!"})
        assert resp.status_code == 400

    def test_single_label_domain_returns_400(self, client):
        # "localhost" has no dot → not a valid registrable domain
        resp = client.post("/allowlist", json={"domain": "localhost"})
        assert resp.status_code == 400


class TestRemoveAllowlistDomain:
    def test_removes_existing_domain(self, client, test_app, mock_col):
        oid = ObjectId()
        doc = make_allowlist_doc()
        doc["_id"] = oid
        mock_col.find_one.return_value = doc
        test_app.state.allowlist_cache.add("khanacademy.org")

        resp = client.delete(f"/allowlist/{oid}")

        assert resp.status_code == 200
        mock_col.delete_one.assert_called_once()

    def test_removes_domain_from_state_cache(self, client, test_app, mock_col):
        oid = ObjectId()
        doc = make_allowlist_doc(domain="khanacademy.org")
        doc["_id"] = oid
        mock_col.find_one.return_value = doc
        test_app.state.allowlist_cache.add("khanacademy.org")

        client.delete(f"/allowlist/{oid}")

        assert "khanacademy.org" not in test_app.state.allowlist_cache

    def test_not_found_returns_404(self, client, mock_col):
        mock_col.find_one.return_value = None
        resp = client.delete(f"/allowlist/{ObjectId()}")
        assert resp.status_code == 404
