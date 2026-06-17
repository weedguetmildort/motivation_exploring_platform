# backend/tests/test_link_health_service.py
"""Unit tests for the link health service: HTTP fetching, relevance, and state transitions."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call
from bson import ObjectId
import httpx
import pytest

from app.services.link_health import (
    fetch_with_retries,
    fetch_page_metadata,
    _first_article_paragraph,
    _is_generic_description,
    _url_slug_description,
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

    def test_401_treated_as_ok_bot_block(self):
        """401/402/403 commonly come from anti-bot/WAF blocks rather than a
        genuinely dead page, so they should not be flagged as failures."""
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(_make_resp(401))):
            ok, code, error = fetch_with_retries("https://example.com/page", max_retries=1, timeout=5)
        assert ok is True
        assert code == 401
        assert error is None

    def test_402_treated_as_ok_bot_block(self):
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(_make_resp(402))):
            ok, code, error = fetch_with_retries("https://example.com/page", max_retries=1, timeout=5)
        assert ok is True
        assert code == 402
        assert error is None

    def test_403_treated_as_ok_bot_block(self):
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(_make_resp(403))):
            ok, code, error = fetch_with_retries("https://example.com/page", max_retries=1, timeout=5)
        assert ok is True
        assert code == 403
        assert error is None

    def test_sends_realistic_browser_headers(self):
        """A bare 'Mozilla/5.0' UA with no Accept headers is itself a bot signal
        to many WAFs — make sure we send a fuller, realistic header set."""
        resp = _make_resp(200)
        ctx = _mock_httpx_client(resp)
        with patch("app.services.link_health.httpx.Client", return_value=ctx) as mock_client_cls:
            fetch_with_retries("https://example.com/page", max_retries=1, timeout=5)

        mock_client = ctx.__enter__.return_value
        _, kwargs = mock_client.get.call_args
        headers = kwargs["headers"]
        assert "Chrome" in headers["User-Agent"]
        assert "Accept" in headers
        assert "Accept-Language" in headers

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


# ── fetch_page_metadata ───────────────────────────────────────────────────────

class TestFetchPageMetadata:
    def _mock_resp(self, html: str, status: int = 200, content_type: str = "text/html; charset=utf-8"):
        resp = MagicMock()
        resp.status_code = status
        resp.text = html
        resp.headers = {"content-type": content_type}
        return resp

    def test_extracts_og_description(self):
        html = '<meta property="og:description" content="OG description here">'
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(self._mock_resp(html))):
            title, desc, excerpt, code = fetch_page_metadata("https://example.com/page", timeout=5)
        assert desc == "OG description here"
        assert code == 200

    def test_og_description_takes_priority_over_meta_name(self):
        html = (
            '<meta name="description" content="Fallback">'
            '<meta property="og:description" content="OG wins">'
        )
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(self._mock_resp(html))):
            _, desc, _, _ = fetch_page_metadata("https://example.com/page", timeout=5)
        assert desc == "OG wins"

    def test_falls_back_to_meta_name_description(self):
        html = '<meta name="description" content="Fallback description">'
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(self._mock_resp(html))):
            _, desc, _, _ = fetch_page_metadata("https://example.com/page", timeout=5)
        assert desc == "Fallback description"

    def test_extracts_og_title(self):
        html = '<meta property="og:title" content="Page Title">'
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(self._mock_resp(html))):
            title, _, _, _ = fetch_page_metadata("https://example.com/page", timeout=5)
        assert title == "Page Title"

    def test_falls_back_to_title_tag(self):
        html = "<title>HTML Title Tag</title>"
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(self._mock_resp(html))):
            title, _, _, _ = fetch_page_metadata("https://example.com/page", timeout=5)
        assert title == "HTML Title Tag"

    def test_extracts_article_excerpt(self):
        html = "<article><p>Short.</p><p>Probability is the mathematical study of uncertainty and random events, covering sample spaces, events, and axioms of probability theory in great detail.</p></article>"
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(self._mock_resp(html))):
            _, _, excerpt, _ = fetch_page_metadata("https://example.com/page", timeout=5)
        assert "Probability" in excerpt

    def test_handles_content_attribute_before_property(self):
        """meta tags sometimes have content= before property= — both orderings must work."""
        html = '<meta content="Reversed content" property="og:description">'
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(self._mock_resp(html))):
            _, desc, _, _ = fetch_page_metadata("https://example.com/page", timeout=5)
        assert desc == "Reversed content"

    def test_returns_empty_for_non_html_content_type(self):
        resp = self._mock_resp("binary content", content_type="application/pdf")
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(resp)):
            title, desc, excerpt, code = fetch_page_metadata("https://example.com/doc.pdf", timeout=5)
        assert title == "" and desc == "" and excerpt == "" and code == 200

    def test_bot_blocked_returns_empty_metadata(self):
        """403 (WAF block) is reachable for fetch_with_retries but yields no parseable HTML."""
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(self._mock_resp("", status=403))):
            title, desc, excerpt, code = fetch_page_metadata("https://example.com/page", timeout=5)
        assert title == "" and desc == "" and excerpt == "" and code == 403

    def test_exception_returns_empty_and_none_code(self):
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("connection failed")
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_client)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("app.services.link_health.httpx.Client", return_value=ctx):
            title, desc, excerpt, code = fetch_page_metadata("https://example.com/page", timeout=5)
        assert title == "" and desc == "" and excerpt == "" and code is None

    def test_clears_generic_gfg_description(self):
        """GeeksforGeeks serves a site-wide meta description that is useless for
        relevance judging — fetch_page_metadata must discard it (return '')."""
        html = (
            '<meta property="og:description" content="Your All-in-One Learning Portal: '
            'GeeksforGeeks is a comprehensive educational platform.">'
        )
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(self._mock_resp(html))):
            _, desc, _, _ = fetch_page_metadata("https://www.geeksforgeeks.org/some-article/", timeout=5)
        assert desc == ""

    def test_uses_url_slug_when_no_article_excerpt(self):
        """When JS rendering hides article content and meta description is empty/generic,
        the URL slug should surface as the excerpt so the judge has something useful."""
        html = "<html><head></head><body><div>No readable paragraphs here.</div></body></html>"
        with patch("app.services.link_health.httpx.Client", return_value=_mock_httpx_client(self._mock_resp(html))):
            _, _, excerpt, _ = fetch_page_metadata(
                "https://www.geeksforgeeks.org/dsa/introduction-to-divide-and-conquer-algorithm/", timeout=5
            )
        assert "Divide" in excerpt
        assert "Conquer" in excerpt


# ── _is_generic_description ───────────────────────────────────────────────────

class TestIsGenericDescription:
    def test_gfg_pattern_detected(self):
        assert _is_generic_description(
            "Your All-in-One Learning Portal: GeeksforGeeks is a comprehensive educational platform."
        ) is True

    def test_case_insensitive(self):
        assert _is_generic_description("YOUR ALL-IN-ONE LEARNING PORTAL") is True

    def test_page_specific_description_not_flagged(self):
        assert _is_generic_description(
            "Divide and Conquer is an algorithm design paradigm that breaks problems into subproblems."
        ) is False

    def test_empty_string_not_flagged(self):
        assert _is_generic_description("") is False


# ── _url_slug_description ─────────────────────────────────────────────────────

class TestUrlSlugDescription:
    def test_humanizes_hyphenated_slug(self):
        result = _url_slug_description(
            "https://www.geeksforgeeks.org/dsa/introduction-to-divide-and-conquer-algorithm/"
        )
        assert result == "Introduction To Divide And Conquer Algorithm"

    def test_skips_generic_trailing_segment(self):
        """When the last segment is a generic word like 'dsa', uses the segment before it."""
        result = _url_slug_description("https://example.com/algorithms/dsa")
        assert result == "Algorithms"

    def test_underscore_separator(self):
        result = _url_slug_description("https://example.com/probability_theory")
        assert result == "Probability Theory"

    def test_empty_for_bare_domain(self):
        assert _url_slug_description("https://example.com/") == ""

    def test_empty_for_unknown_generic_only(self):
        assert _url_slug_description("https://example.com/index") == ""


# ── _first_article_paragraph ──────────────────────────────────────────────────

class TestFirstArticleParagraph:
    LONG = "Probability is the mathematical study of random events and uncertainty, covering sample spaces, axioms, and distributions."

    def test_extracts_from_article_tag(self):
        html = f"<article><p>Short.</p><p>{self.LONG}</p></article>"
        assert self.LONG in _first_article_paragraph(html)

    def test_extracts_from_main_tag(self):
        html = f"<main><p>{self.LONG}</p></main>"
        assert self.LONG in _first_article_paragraph(html)

    def test_skips_short_paragraphs(self):
        html = f"<article><p>Nav item.</p><p>Also short.</p><p>{self.LONG}</p></article>"
        result = _first_article_paragraph(html)
        assert result == self.LONG[:500]

    def test_strips_html_tags(self):
        html = f"<article><p>{self.LONG} <a href='/'>link</a> text</p></article>"
        result = _first_article_paragraph(html)
        assert "<a" not in result
        assert "link" in result

    def test_caps_at_500_chars(self):
        long_text = "A" * 600
        html = f"<article><p>{long_text}</p></article>"
        result = _first_article_paragraph(html)
        assert len(result) == 500

    def test_returns_empty_when_no_long_paragraph(self):
        html = "<article><p>Short.</p><p>Also short.</p></article>"
        assert _first_article_paragraph(html) == ""

    def test_falls_back_to_full_page_when_no_semantic_wrapper(self):
        html = f"<html><body><p>{self.LONG}</p></body></html>"
        assert self.LONG in _first_article_paragraph(html)


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
        relevant, reason = is_relevant("Basic Probability", link, client, {"khanacademy.org"})
        assert relevant is False
        assert reason == "domain_not_allowed"
        client.chat.completions.create.assert_not_called()  # LLM never reached

    def test_domain_allowed_and_llm_says_yes(self):
        client = MagicMock()
        choice = MagicMock()
        choice.message.content = "YES"
        client.chat.completions.create.return_value = MagicMock(choices=[choice])

        link = {"url": "https://khanacademy.org/probability", "title": "Probability", "description": "Coin flips"}
        relevant, reason = is_relevant("Basic Probability", link, client, {"khanacademy.org"})
        assert relevant is True
        assert reason is None

    def test_domain_allowed_but_llm_says_no(self):
        client = MagicMock()
        choice = MagicMock()
        choice.message.content = "NO"
        client.chat.completions.create.return_value = MagicMock(choices=[choice])

        link = {"url": "https://khanacademy.org/calculus", "title": "Calculus", "description": "Derivatives"}
        relevant, reason = is_relevant("Basic Probability", link, client, {"khanacademy.org"})
        assert relevant is False
        assert reason == "irrelevant"


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
             patch("app.services.link_health.is_relevant", return_value=(True, None)):
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
             patch("app.services.link_health.is_relevant", return_value=(True, None)):
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
        """A READY link on a now-untrusted domain should move to NOT_READY, tagged
        with the specific 'domain_not_allowed' reason (not a generic 'irrelevant')."""
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
             patch("app.services.link_health.is_relevant", return_value=(False, "domain_not_allowed")):
            result = run_health_check(db, self._settings(), MagicMock(), set())

        assert result["degraded"] == 1
        update = col.update_one.call_args[0][1]["$set"]
        assert update["status"] == "NOT_READY"
        assert update["last_error_type"] == "domain_not_allowed"

    def test_ready_link_llm_judges_irrelevant_degrades_with_reason(self):
        """A READY link on a trusted domain whose content the LLM judges off-topic
        should move to NOT_READY, tagged 'irrelevant' — distinct from a domain-trust
        failure so admins can tell which gate actually blocked the link."""
        link = {
            "_id": ObjectId(),
            "url": "https://khanacademy.org/calculus",
            "status": "READY",
            "tags": ["Basic Probability"],
            "title": "Calculus",
            "description": "Derivatives",
        }
        col = self._setup_col([link])
        db = self._setup_db(col)

        # fetch succeeds and domain is trusted, but the LLM says the content is off-topic
        with patch("app.services.link_health.fetch_with_retries", return_value=(True, 200, None)), \
             patch("app.services.link_health.is_relevant", return_value=(False, "irrelevant")):
            result = run_health_check(db, self._settings(), MagicMock(), {"khanacademy.org"})

        assert result["degraded"] == 1
        update = col.update_one.call_args[0][1]["$set"]
        assert update["status"] == "NOT_READY"
        assert update["last_error_type"] == "irrelevant"

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
             patch("app.services.link_health.is_relevant", return_value=(True, None)):  # called once (link 3)
            result = run_health_check(db, self._settings(), MagicMock(), {"a.com", "b.com", "c.com"})

        assert result["checked"] == 3
        assert result["degraded"] == 2
        assert result["recovered"] == 1
