# backend/tests/test_link_health_service.py
"""Unit tests for the link health service: HTTP fetching, relevance, and state transitions."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call
from bson import ObjectId
import httpx
import pytest

from app.services.link_health import (
    fetch_with_retries,
    llm_judges_relevant,
    is_relevant,
    run_health_check,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_resp(status_code, url="https://example.com/page"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.url = url
    return resp


def _mock_httpx_client(resp):
    """Return a context-manager mock that yields a client whose .get() returns resp."""
    mock_client = MagicMock()
    mock_client.get.return_value = resp
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_client)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


# ── fetch_with_retries ────────────────────────────────────────────────────────

class TestFetchWithRetries:
    def test_200_returns_ok(self):
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(_make_resp(200))):
            ok, code, error = fetch_with_retries("https://example.com/page", max_retries=1, timeout=5)
        assert ok is True
        assert code == 200
        assert error is None

    def test_404_returns_http_error(self):
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(_make_resp(404))):
            ok, code, error = fetch_with_retries("https://example.com/gone", max_retries=1, timeout=5)
        assert ok is False
        assert code == 404
        assert error == "http_error"

    def test_500_returns_http_error(self):
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(_make_resp(500))):
            ok, code, error = fetch_with_retries("https://example.com", max_retries=1, timeout=5)
        assert ok is False
        assert code == 500
        assert error == "http_error"

    def test_redirect_to_root_returns_redirect_root(self):
        # Original URL has a path; final URL is the bare root → page was removed
        resp = _make_resp(301, url="https://example.com")  # final URL has no path
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(resp)):
            ok, code, error = fetch_with_retries("https://example.com/specific-page", max_retries=1, timeout=5)
        assert ok is False
        assert error == "redirect_root"

    def test_redirect_to_different_path_is_ok(self):
        # Redirect to a different valid path is fine (not a root-redirect)
        resp = _make_resp(301, url="https://example.com/new-location")
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(resp)):
            ok, code, error = fetch_with_retries("https://example.com/old-location", max_retries=1, timeout=5)
        assert ok is True

    def test_timeout_retries_and_fails(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.TimeoutException("timed out")
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_client)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch("app.services.link_health.httpx.Client", return_value=ctx), \
             patch("time.sleep"):  # skip actual delays
            ok, code, error = fetch_with_retries("https://example.com", max_retries=3, timeout=5)

        assert ok is False
        assert code is None
        assert error == "timeout"
        assert mock_client.get.call_count == 3  # retried max_retries times

    def test_connect_error_retries_and_fails(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("connection refused")
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_client)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch("app.services.link_health.httpx.Client", return_value=ctx), \
             patch("time.sleep"):
            ok, code, error = fetch_with_retries("https://example.com", max_retries=2, timeout=5)

        assert ok is False
        assert error == "connection_error"
        assert mock_client.get.call_count == 2

    def test_unknown_exception_fails_open(self):
        """Unknown errors (e.g., SSL issues on protected sites) should NOT mark the link dead."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("ssl certificate verify failed")
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_client)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch("app.services.link_health.httpx.Client", return_value=ctx):
            ok, code, error = fetch_with_retries("https://protected.gov/resource", max_retries=1, timeout=5)

        assert ok is True  # fail-open: don't penalize protected/unknown sites
        assert code is None
        assert error is None


# ── llm_judges_relevant ───────────────────────────────────────────────────────

class TestLlmJudgesRelevant:
    def _make_client(self, content):
        client = MagicMock()
        choice = MagicMock()
        choice.message.content = content
        client.chat.completions.create.return_value = MagicMock(choices=[choice])
        return client

    def test_yes_returns_true(self):
        client = self._make_client("YES")
        assert llm_judges_relevant("Basic Probability", "Intro to Probability", "Covers basic probability", client) is True

    def test_no_returns_false(self):
        client = self._make_client("NO")
        assert llm_judges_relevant("Basic Probability", "Advanced Calculus", "Integrals and derivatives", client) is False

    def test_case_insensitive(self):
        client = self._make_client("yes, it is relevant")
        assert llm_judges_relevant("Basic Probability", "Probability Basics", "Covers coin flips", client) is True

    def test_llm_failure_fails_open(self):
        """If the LLM call fails, we keep the link rather than dropping it incorrectly."""
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("API error")
        assert llm_judges_relevant("Basic Probability", "Some Title", "Some desc", client) is True


# ── is_relevant ───────────────────────────────────────────────────────────────

class TestIsRelevant:
    def test_domain_not_in_allowlist_blocked_before_llm(self):
        client = MagicMock()
        link = {"url": "https://shady-site.net/prob", "title": "Prob", "description": "stuff"}
        result = is_relevant("Basic Probability", link, client, {"khanacademy.org"})
        assert result is False
        client.chat.completions.create.assert_not_called()  # LLM never reached

    def test_domain_allowed_and_llm_says_yes(self):
        client = MagicMock()
        choice = MagicMock()
        choice.message.content = "YES"
        client.chat.completions.create.return_value = MagicMock(choices=[choice])

        link = {"url": "https://khanacademy.org/probability", "title": "Probability", "description": "Coin flips"}
        result = is_relevant("Basic Probability", link, client, {"khanacademy.org"})
        assert result is True

    def test_domain_allowed_but_llm_says_no(self):
        client = MagicMock()
        choice = MagicMock()
        choice.message.content = "NO"
        client.chat.completions.create.return_value = MagicMock(choices=[choice])

        link = {"url": "https://khanacademy.org/calculus", "title": "Calculus", "description": "Derivatives"}
        result = is_relevant("Basic Probability", link, client, {"khanacademy.org"})
        assert result is False


# ── run_health_check — state transitions ──────────────────────────────────────

class TestRunHealthCheckTransitions:
    def _setup_col(self, links):
        col = MagicMock()
        col.find.return_value = links
        return col

    def _setup_db(self, col):
        db = MagicMock()
        db.__getitem__ = MagicMock(return_value=col)
        return db

    def _settings(self):
        s = MagicMock()
        s.MAX_RETRIES_LINK_CHECK = 1
        s.LINK_REQUEST_TIMEOUT = 5
        return s

    def test_ready_link_fails_moves_to_not_ready(self):
        link = {
            "_id": ObjectId(),
            "url": "https://khanacademy.org/broken",
            "status": "READY",
            "tags": ["Basic Probability"],
            "title": "Broken page",
            "description": "Gone",
        }
        col = self._setup_col([link])
        db = self._setup_db(col)

        with patch("app.services.link_health.fetch_with_retries", return_value=(False, 404, "http_error")), \
             patch("app.services.link_health.is_relevant", return_value=False):
            result = run_health_check(db, self._settings(), MagicMock(), {"khanacademy.org"})

        assert result["degraded"] == 1
        assert result["recovered"] == 0
        update = col.update_one.call_args[0][1]["$set"]
        assert update["status"] == "NOT_READY"
        assert update["last_http_code"] == 404

    def test_ready_link_passes_stays_ready(self):
        link = {
            "_id": ObjectId(),
            "url": "https://khanacademy.org/prob",
            "status": "READY",
            "tags": ["Basic Probability"],
            "title": "Probability",
            "description": "Good content",
        }
        col = self._setup_col([link])
        db = self._setup_db(col)

        with patch("app.services.link_health.fetch_with_retries", return_value=(True, 200, None)), \
             patch("app.services.link_health.is_relevant", return_value=True):
            result = run_health_check(db, self._settings(), MagicMock(), {"khanacademy.org"})

        assert result["degraded"] == 0
        # update_one is still called with last_checked, but status is NOT in the update
        update = col.update_one.call_args[0][1]["$set"]
        assert "status" not in update
        assert "last_checked" in update

    def test_not_ready_link_recovers_to_needs_review(self):
        """A revived link goes to NEEDS_REVIEW (not straight back to READY)."""
        link = {
            "_id": ObjectId(),
            "url": "https://khanacademy.org/prob",
            "status": "NOT_READY",
            "tags": ["Basic Probability"],
            "title": "Probability",
            "description": "Good content",
        }
        col = self._setup_col([link])
        db = self._setup_db(col)

        with patch("app.services.link_health.fetch_with_retries", return_value=(True, 200, None)), \
             patch("app.services.link_health.is_relevant", return_value=True):
            result = run_health_check(db, self._settings(), MagicMock(), {"khanacademy.org"})

        assert result["recovered"] == 1
        update = col.update_one.call_args[0][1]["$set"]
        assert update["status"] == "NEEDS_REVIEW"  # never auto-promoted to READY

    def test_not_ready_link_still_dead_stays_not_ready(self):
        link = {
            "_id": ObjectId(),
            "url": "https://khanacademy.org/broken",
            "status": "NOT_READY",
            "tags": ["Basic Probability"],
            "title": "Broken",
            "description": "Still dead",
        }
        col = self._setup_col([link])
        db = self._setup_db(col)

        with patch("app.services.link_health.fetch_with_retries", return_value=(False, 404, "http_error")), \
             patch("app.services.link_health.is_relevant", return_value=False):
            result = run_health_check(db, self._settings(), MagicMock(), {"khanacademy.org"})

        assert result["degraded"] == 0
        assert result["recovered"] == 0
        update = col.update_one.call_args[0][1]["$set"]
        assert "status" not in update  # NOT_READY stays NOT_READY

    def test_ready_link_domain_not_in_allowlist_degrades(self):
        """A READY link on a now-untrusted domain should move to NOT_READY."""
        link = {
            "_id": ObjectId(),
            "url": "https://removed-domain.com/prob",
            "status": "READY",
            "tags": ["Basic Probability"],
            "title": "Probability",
            "description": "Content",
        }
        col = self._setup_col([link])
        db = self._setup_db(col)

        # fetch succeeds but is_relevant fails (domain not in allowlist)
        with patch("app.services.link_health.fetch_with_retries", return_value=(True, 200, None)), \
             patch("app.services.link_health.is_relevant", return_value=False):
            result = run_health_check(db, self._settings(), MagicMock(), set())

        assert result["degraded"] == 1
        update = col.update_one.call_args[0][1]["$set"]
        assert update["status"] == "NOT_READY"

    def test_summary_counts_multiple_links(self):
        """Two READY links fail (degraded), one NOT_READY link recovers.
        is_relevant is only called when ok=True (Python short-circuit), so it's
        only invoked for the third link (the NOT_READY one that passes fetch).
        """
        links = [
            {
                "_id": ObjectId(), "url": "https://a.com/1", "status": "READY",
                "tags": ["Basic Probability"], "title": "A", "description": "D",
            },
            {
                "_id": ObjectId(), "url": "https://b.com/2", "status": "READY",
                "tags": ["Basic Probability"], "title": "B", "description": "D",
            },
            {
                "_id": ObjectId(), "url": "https://c.com/3", "status": "NOT_READY",
                "tags": ["Basic Probability"], "title": "C", "description": "D",
            },
        ]
        col = self._setup_col(links)
        db = self._setup_db(col)

        fetch_results = [(False, 404, "http_error"), (False, 404, "http_error"), (True, 200, None)]

        with patch("app.services.link_health.fetch_with_retries", side_effect=fetch_results), \
             patch("app.services.link_health.is_relevant", return_value=True):  # called once (link 3)
            result = run_health_check(db, self._settings(), MagicMock(), {"a.com", "b.com", "c.com"})

        assert result["checked"] == 3
        assert result["degraded"] == 2
        assert result["recovered"] == 1
