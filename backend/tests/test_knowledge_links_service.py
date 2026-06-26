# backend/tests/test_knowledge_links_service.py
"""Unit tests for the knowledge-links service: CRUD, approve/reject, cache, tag normalization."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch
from bson import ObjectId
import pytest

from app.schemas.knowledge_link import KnowledgeLinkCreate, KnowledgeLinkUpdate, LinkStatus
from app.services.knowledge_links import (
    normalize_tags,
    create_knowledge_link,
    approve_link,
    reject_link,
    explore_link,
    apply_explore,
    reload_knowledge_links_cache,
    list_knowledge_links_by_status,
    update_knowledge_link,
    delete_knowledge_link,
)


# ── normalize_tags ────────────────────────────────────────────────────────────

class TestNormalizeTags:
    def test_preserves_original_case(self):
        result = normalize_tags(["Basic Probability"])
        assert result == ["Basic Probability"]

    def test_deduplicates_case_insensitively(self):
        result = normalize_tags(["Basic Probability", "basic probability", "BASIC PROBABILITY"])
        assert result == ["Basic Probability"]

    def test_strips_whitespace(self):
        result = normalize_tags(["  Basic Probability  "])
        assert result == ["Basic Probability"]

    def test_preserves_order(self):
        tags = ["Conditional Probability", "Basic Probability"]
        result = normalize_tags(tags)
        assert result == ["Conditional Probability", "Basic Probability"]

    def test_empty_list_returns_empty(self):
        assert normalize_tags([]) == []

    def test_stored_case_matches_predefined_tags(self):
        """Tags must be stored with original casing so discovery queries match."""
        from app.services.link_health import PREDEFINED_TAGS
        for tag in PREDEFINED_TAGS:
            result = normalize_tags([tag])
            assert result == [tag], f"Tag '{tag}' lost its casing after normalize_tags"


# ── create_knowledge_link ─────────────────────────────────────────────────────

class TestCreateKnowledgeLink:
    def test_creates_with_ready_status(self):
        col = MagicMock()
        oid = ObjectId()
        col.insert_one.return_value = MagicMock(inserted_id=oid)

        data = KnowledgeLinkCreate(
            title="Probability Intro",
            url="https://khanacademy.org/probability",
            description="Good introduction to probability.",
            tags=["Basic Probability"],
        )
        result = create_knowledge_link(col, data)

        assert result.status == LinkStatus.READY
        assert result.title == "Probability Intro"
        assert result.tags == ["Basic Probability"]

    def test_sets_active_true(self):
        col = MagicMock()
        col.insert_one.return_value = MagicMock(inserted_id=ObjectId())

        data = KnowledgeLinkCreate(
            title="Test",
            url="https://example.com",
            description="Desc",
            tags=["Other"],
        )
        create_knowledge_link(col, data)

        inserted_doc = col.insert_one.call_args[0][0]
        assert inserted_doc["active"] is True
        assert inserted_doc["status"] == "READY"

    def test_trims_whitespace_from_fields(self):
        col = MagicMock()
        col.insert_one.return_value = MagicMock(inserted_id=ObjectId())

        data = KnowledgeLinkCreate(
            title="  Trimmed Title  ",
            url="https://example.com",
            description="  Trimmed desc  ",
            tags=["Basic Probability"],
        )
        create_knowledge_link(col, data)

        doc = col.insert_one.call_args[0][0]
        assert doc["title"] == "Trimmed Title"
        assert doc["description"] == "Trimmed desc"


# ── approve_link ──────────────────────────────────────────────────────────────

class TestApproveLink:
    def _make_col(self, oid, status="NEEDS_REVIEW"):
        doc = {
            "_id": oid,
            "title": "Test",
            "url": "https://example.com",
            "tags": ["Basic Probability"],
            "description": "Desc",
            "status": status,
        }
        col = MagicMock()
        # First find_one (by id+status) returns the doc, second (re-read) returns updated
        ready_doc = {**doc, "status": "READY", "active": True}
        col.find_one.side_effect = [doc, ready_doc]
        return col

    def test_needs_review_moves_to_ready(self):
        oid = ObjectId()
        col = self._make_col(oid)

        result = approve_link(col, str(oid))

        assert result is not None
        assert result.status == LinkStatus.READY
        update_args = col.update_one.call_args[0][1]["$set"]
        assert update_args["status"] == "READY"
        assert update_args["active"] is True

    def test_returns_none_for_invalid_id(self):
        col = MagicMock()
        assert approve_link(col, "not-an-objectid") is None
        col.find_one.assert_not_called()

    def test_returns_none_when_not_needs_review(self):
        oid = ObjectId()
        col = MagicMock()
        col.find_one.return_value = None  # Query with status=NEEDS_REVIEW returns nothing

        result = approve_link(col, str(oid))
        assert result is None
        col.update_one.assert_not_called()


# ── reject_link ───────────────────────────────────────────────────────────────

class TestRejectLink:
    def _make_col_for_reject(self, oid, status):
        doc = {
            "_id": oid,
            "title": "Test",
            "url": "https://example.com",
            "tags": ["Basic Probability"],
            "description": "Desc",
            "status": status,
        }
        col = MagicMock()
        rejected_doc = {**doc, "status": "REJECTED", "active": False}
        col.find_one.side_effect = [doc, rejected_doc]
        return col

    def test_needs_review_can_be_rejected(self):
        oid = ObjectId()
        col = self._make_col_for_reject(oid, "NEEDS_REVIEW")

        result = reject_link(col, str(oid))

        assert result is not None
        assert result.status == LinkStatus.REJECTED
        update = col.update_one.call_args[0][1]["$set"]
        assert update["status"] == "REJECTED"
        assert update["active"] is False

    def test_not_ready_can_be_rejected(self):
        oid = ObjectId()
        col = self._make_col_for_reject(oid, "NOT_READY")

        result = reject_link(col, str(oid))
        assert result.status == LinkStatus.REJECTED

    def test_ready_link_cannot_be_rejected(self):
        oid = ObjectId()
        col = MagicMock()
        # Query filters on status in [NEEDS_REVIEW, NOT_READY] → returns None for READY
        col.find_one.return_value = None

        result = reject_link(col, str(oid))
        assert result is None
        col.update_one.assert_not_called()

    def test_returns_none_for_invalid_id(self):
        col = MagicMock()
        assert reject_link(col, "bad-id") is None


# ── reload_knowledge_links_cache ──────────────────────────────────────────────

class TestReloadKnowledgeLinksCache:
    def test_returns_only_ready_links(self):
        oid1, oid2 = ObjectId(), ObjectId()
        col = MagicMock()
        col.find.return_value = [
            {"_id": oid1, "title": "Link A", "url": "https://a.com", "description": "D"},
            {"_id": oid2, "title": "Link B", "url": "https://b.com", "description": "E"},
        ]

        result = reload_knowledge_links_cache(col)

        col.find.assert_called_once_with({"status": "READY"})
        assert len(result) == 2
        assert result[0]["title"] == "Link A"
        assert result[0]["url"] == "https://a.com"
        assert result[0]["id"] == str(oid1)

    def test_returns_correct_shape(self):
        oid = ObjectId()
        col = MagicMock()
        col.find.return_value = [{"_id": oid, "title": "T", "url": "https://x.com", "description": "D"}]

        result = reload_knowledge_links_cache(col)
        entry = result[0]
        assert set(entry.keys()) == {"id", "title", "url", "description"}

    def test_empty_collection_returns_empty_list(self):
        col = MagicMock()
        col.find.return_value = []
        assert reload_knowledge_links_cache(col) == []


# ── list_knowledge_links_by_status ────────────────────────────────────────────

class TestListKnowledgeLinksByStatus:
    def _ready_doc(self):
        return {
            "_id": ObjectId(),
            "title": "T",
            "url": "https://example.com",
            "tags": ["Basic Probability"],
            "description": "D",
            "status": "READY",
        }

    def test_none_status_returns_all(self):
        col = MagicMock()
        col.find.return_value.sort.return_value = [self._ready_doc()]
        results = list_knowledge_links_by_status(col, None)
        assert len(results) == 1
        # Called without status filter
        col.find.assert_called_once_with()

    def test_specific_status_filters(self):
        col = MagicMock()
        col.find.return_value.sort.return_value = [self._ready_doc()]
        results = list_knowledge_links_by_status(col, "NEEDS_REVIEW")
        col.find.assert_called_once_with({"status": "NEEDS_REVIEW"})

    def test_to_public_maps_status_correctly(self):
        col = MagicMock()
        doc = self._ready_doc()
        col.find.return_value.sort.return_value = [doc]
        results = list_knowledge_links_by_status(col, None)
        assert results[0].status == LinkStatus.READY


# ── explore_link (preview — no DB writes) ────────────────────────────────────

class TestExploreLink:
    def _make_doc(self, oid, status="READY"):
        return {
            "_id": oid,
            "title": "Link Title",
            "url": "https://khanacademy.org/probability",
            "tags": ["Basic Probability"],
            "description": "Short desc",
            "status": status,
        }

    def _make_col(self, oid, status="READY"):
        doc = self._make_doc(oid, status)
        col = MagicMock()
        col.find_one.return_value = doc
        return col, doc

    def test_returns_none_for_invalid_id(self):
        col = MagicMock()
        result = explore_link(col, "not-an-objectid", MagicMock(), set())
        assert result is None
        col.find_one.assert_not_called()

    def test_returns_none_for_rejected_link(self):
        oid = ObjectId()
        col, _ = self._make_col(oid, status="REJECTED")
        result = explore_link(col, str(oid), MagicMock(), set())
        assert result is None

    def test_does_not_write_to_db(self):
        """explore_link is a preview-only operation — it must not touch the database."""
        oid = ObjectId()
        col, _ = self._make_col(oid)
        with patch("app.services.link_health.fetch_page_metadata", return_value=("T", "D", "E", 200)), \
             patch("app.services.link_health.is_relevant", return_value=(True, None)):
            explore_link(col, str(oid), MagicMock(), set())
        col.update_one.assert_not_called()

    def test_returns_explore_preview_with_fetched_content(self):
        oid = ObjectId()
        col, _ = self._make_col(oid)
        with patch("app.services.link_health.fetch_page_metadata", return_value=("Fetched Title", "Fetched desc", "Article para", 200)), \
             patch("app.services.link_health.is_relevant", return_value=(True, None)):
            result = explore_link(col, str(oid), MagicMock(), set())
        assert result.proposed_title == "Fetched Title"
        assert result.proposed_description == "Fetched desc"
        assert result.article_excerpt == "Article para"
        assert result.http_code == 200

    def test_relevant_flag_reflects_judge_verdict(self):
        oid = ObjectId()
        col, _ = self._make_col(oid)
        with patch("app.services.link_health.fetch_page_metadata", return_value=("", "Some desc", "", 200)), \
             patch("app.services.link_health.is_relevant", return_value=(False, "irrelevant")):
            result = explore_link(col, str(oid), MagicMock(), set())
        assert result.relevant is False
        assert result.relevance_reason == "irrelevant"

    def test_falls_back_to_stored_description_for_judge_when_fetch_empty(self):
        """When the page returns nothing useful (including Jina), judge runs using stored description."""
        oid = ObjectId()
        col, doc = self._make_col(oid)
        mock_relevant = MagicMock(return_value=(True, None))
        with patch("app.services.link_health.fetch_page_metadata", return_value=("", "", "", 403)), \
             patch("app.services.link_health.fetch_readable_content", return_value=""), \
             patch("app.services.link_health.is_relevant", mock_relevant):
            explore_link(col, str(oid), MagicMock(), set())
        link_arg = mock_relevant.call_args[0][1]
        assert link_arg["description"] == doc["description"]

    def test_uses_ai_summary_when_meta_description_missing(self):
        """When meta description is absent, Jina content is fetched and the LLM
        generates a proper summary to use as the proposed description."""
        oid = ObjectId()
        col, _ = self._make_col(oid)
        with patch("app.services.link_health.fetch_page_metadata", return_value=("D&C Title", "", "", 200)), \
             patch("app.services.link_health.fetch_readable_content", return_value="Divide and conquer splits a problem..."), \
             patch("app.services.link_health.summarize_page_content", return_value="Covers divide and conquer algorithm design."), \
             patch("app.services.link_health.is_relevant", return_value=(True, None)):
            result = explore_link(col, str(oid), MagicMock(), set())
        assert result.proposed_description == "Covers divide and conquer algorithm design."

    def test_sets_article_excerpt_from_readable_content_when_body_empty(self):
        """When article body extraction finds nothing but Jina returns content,
        the first 500 chars of the readable content are used as the excerpt."""
        oid = ObjectId()
        col, _ = self._make_col(oid)
        jina_text = "Readable content from Jina " * 5
        with patch("app.services.link_health.fetch_page_metadata", return_value=("Title", "", "", 200)), \
             patch("app.services.link_health.fetch_readable_content", return_value=jina_text), \
             patch("app.services.link_health.summarize_page_content", return_value="Summary."), \
             patch("app.services.link_health.is_relevant", return_value=(True, None)):
            result = explore_link(col, str(oid), MagicMock(), set())
        assert result.article_excerpt == jina_text[:500]


# ── apply_explore (saves confirmed content) ───────────────────────────────────

class TestApplyExplore:
    def _make_doc(self, oid, status="READY"):
        return {
            "_id": oid,
            "title": "Old Title",
            "url": "https://khanacademy.org/probability",
            "tags": ["Basic Probability"],
            "description": "Old short desc",
            "status": status,
        }

    def _make_col(self, oid, status="READY"):
        doc = self._make_doc(oid, status)
        col = MagicMock()
        col.find_one.return_value = doc
        return col, doc

    def test_returns_none_for_invalid_id(self):
        col = MagicMock()
        result = apply_explore(col, "bad-id", "T", "D", MagicMock(), set())
        assert result is None

    def test_returns_none_for_rejected_link(self):
        oid = ObjectId()
        col, _ = self._make_col(oid, status="REJECTED")
        result = apply_explore(col, str(oid), "T", "D", MagicMock(), set())
        assert result is None
        col.update_one.assert_not_called()

    def test_saves_new_title_and_description(self):
        oid = ObjectId()
        col, original_doc = self._make_col(oid)
        updated_doc = {**original_doc, "title": "New Title", "description": "Better description"}
        col.find_one.side_effect = [original_doc, updated_doc]
        with patch("app.services.link_health.is_relevant", return_value=(True, None)):
            apply_explore(col, str(oid), "New Title", "Better description", MagicMock(), set())
        update_args = col.update_one.call_args[0][1]["$set"]
        assert update_args["title"] == "New Title"
        assert update_args["description"] == "Better description"

    def test_ready_link_demoted_when_judge_says_irrelevant(self):
        oid = ObjectId()
        col, original_doc = self._make_col(oid, status="READY")
        col.find_one.side_effect = [original_doc, {**original_doc, "status": "NOT_READY"}]
        with patch("app.services.link_health.is_relevant", return_value=(False, "irrelevant")):
            apply_explore(col, str(oid), "T", "D", MagicMock(), set())
        update_args = col.update_one.call_args[0][1]["$set"]
        assert update_args["status"] == "NOT_READY"
        assert update_args["last_error_type"] == "irrelevant"

    def test_not_ready_link_promoted_to_needs_review(self):
        oid = ObjectId()
        col, original_doc = self._make_col(oid, status="NOT_READY")
        col.find_one.side_effect = [original_doc, {**original_doc, "status": "NEEDS_REVIEW"}]
        with patch("app.services.link_health.is_relevant", return_value=(True, None)):
            apply_explore(col, str(oid), "T", "Good description", MagicMock(), set())
        update_args = col.update_one.call_args[0][1]["$set"]
        assert update_args["status"] == "NEEDS_REVIEW"
        assert update_args["last_error_type"] is None

    def test_ready_link_stays_ready_when_judge_approves(self):
        oid = ObjectId()
        col, original_doc = self._make_col(oid, status="READY")
        col.find_one.side_effect = [original_doc, original_doc]
        with patch("app.services.link_health.is_relevant", return_value=(True, None)):
            apply_explore(col, str(oid), "T", "D", MagicMock(), set())
        update_args = col.update_one.call_args[0][1]["$set"]
        assert "status" not in update_args
        assert update_args.get("last_error_type") is None


# ── update_knowledge_link — status not overwritten ────────────────────────────

class TestUpdateKnowledgeLink:
    def test_update_does_not_change_status(self):
        """update_knowledge_link must never overwrite status — that's for approve/reject."""
        oid = ObjectId()
        existing = {
            "_id": oid, "title": "Old", "url": "https://example.com",
            "tags": ["Basic Probability"], "description": "Old", "status": "NEEDS_REVIEW",
        }
        updated = {**existing, "title": "New", "status": "NEEDS_REVIEW"}
        col = MagicMock()
        col.find_one.side_effect = [existing, updated]

        data = KnowledgeLinkUpdate(
            title="New",
            url="https://example.com",
            description="Old",
            tags=["Basic Probability"],
        )
        update_knowledge_link(col, str(oid), data)

        set_doc = col.update_one.call_args[0][1]["$set"]
        assert "status" not in set_doc
