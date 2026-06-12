# backend/tests/test_search_service.py
"""Unit tests for app.services.search: Tavily search, URL validation,
search-context building, and citation injection."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.search import (
    _run_search,
    _check_url,
    _filter_valid_urls,
    _build_search_context,
    _title_keywords,
    _unlinked_search,
    _place_marker_inline,
    _inject_citation_links,
    get_chat_response_with_search,
)


# ── _run_search ───────────────────────────────────────────────────────────────

class TestRunSearch:
    def test_no_api_key_returns_empty_without_http_call(self, monkeypatch):
        monkeypatch.setattr("app.services.search._TAVILY_API_KEY", "")

        with patch("app.services.search.httpx.AsyncClient") as mock_client_cls:
            result = asyncio.run(_run_search("probability"))

        assert result == []
        mock_client_cls.assert_not_called()

    def test_successful_response_returns_mapped_results(self, monkeypatch):
        monkeypatch.setattr("app.services.search._TAVILY_API_KEY", "test-key")

        fake_resp = MagicMock()
        fake_resp.is_success = True
        fake_resp.status_code = 200
        fake_resp.text = "ok"
        fake_resp.raise_for_status = MagicMock()
        fake_resp.json.return_value = {
            "results": [
                {"title": "Khan Academy", "url": "https://khanacademy.org/math", "content": "Learn math"},
                {"title": "Wikipedia", "url": "https://wikipedia.org/wiki/Probability", "content": "Probability article"},
            ]
        }

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.search.httpx.AsyncClient", return_value=mock_client_cm):
            result = asyncio.run(_run_search("probability"))

        assert result == [
            {"title": "Khan Academy", "url": "https://khanacademy.org/math", "snippet": "Learn math"},
            {"title": "Wikipedia", "url": "https://wikipedia.org/wiki/Probability", "snippet": "Probability article"},
        ]
        mock_client.post.assert_awaited_once()

    def test_http_failure_returns_empty(self, monkeypatch):
        monkeypatch.setattr("app.services.search._TAVILY_API_KEY", "test-key")

        fake_resp = MagicMock()
        fake_resp.is_success = False
        fake_resp.status_code = 500
        fake_resp.text = "Internal Server Error"
        fake_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=fake_resp
        )

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.search.httpx.AsyncClient", return_value=mock_client_cm):
            result = asyncio.run(_run_search("probability"))

        assert result == []

    def test_exception_during_request_returns_empty(self, monkeypatch):
        monkeypatch.setattr("app.services.search._TAVILY_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection failed"))
        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.search.httpx.AsyncClient", return_value=mock_client_cm):
            result = asyncio.run(_run_search("probability"))

        assert result == []

    def test_max_results_capped_at_20(self, monkeypatch):
        monkeypatch.setattr("app.services.search._TAVILY_API_KEY", "test-key")

        fake_resp = MagicMock()
        fake_resp.is_success = True
        fake_resp.status_code = 200
        fake_resp.text = "ok"
        fake_resp.raise_for_status = MagicMock()
        fake_resp.json.return_value = {"results": []}

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.search.httpx.AsyncClient", return_value=mock_client_cm):
            asyncio.run(_run_search("probability", max_results=50))

        _, kwargs = mock_client.post.call_args
        assert kwargs["json"]["max_results"] == 20


# ── _check_url ────────────────────────────────────────────────────────────────

def _make_stream_client(fake_response, raise_exc=None):
    """Build a fake httpx-like client whose .stream() is an async context manager."""
    client = MagicMock()
    if raise_exc is not None:
        stream_cm = MagicMock()
        stream_cm.__aenter__ = AsyncMock(side_effect=raise_exc)
        stream_cm.__aexit__ = AsyncMock(return_value=False)
    else:
        stream_cm = MagicMock()
        stream_cm.__aenter__ = AsyncMock(return_value=fake_response)
        stream_cm.__aexit__ = AsyncMock(return_value=False)
    client.stream = MagicMock(return_value=stream_cm)
    return client


class TestCheckUrl:
    def test_404_returns_invalid(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 404
        fake_resp.url = "https://example.com/missing-page"
        client = _make_stream_client(fake_resp)

        result = asyncio.run(_check_url("https://example.com/missing-page", client))

        assert result == ("https://example.com/missing-page", False)

    def test_redirect_to_root_returns_invalid(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.url = "https://example.com/"
        client = _make_stream_client(fake_resp)

        result = asyncio.run(_check_url("https://example.com/some/deep/page", client))

        assert result == ("https://example.com/some/deep/page", False)

    def test_normal_200_same_path_returns_valid(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.url = "https://example.com/some/deep/page"
        client = _make_stream_client(fake_resp)

        result = asyncio.run(_check_url("https://example.com/some/deep/page", client))

        assert result == ("https://example.com/some/deep/page", True)

    def test_root_url_redirect_to_root_is_valid(self):
        # original path is empty, so the "redirect to root" check doesn't apply
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.url = "https://example.com/"
        client = _make_stream_client(fake_resp)

        result = asyncio.run(_check_url("https://example.com/", client))

        assert result == ("https://example.com/", True)

    def test_exception_returns_valid(self):
        client = _make_stream_client(None, raise_exc=httpx.ConnectError("boom"))

        result = asyncio.run(_check_url("https://example.com/page", client))

        assert result == ("https://example.com/page", True)


# ── _filter_valid_urls ──────────────────────────────────────────────────────────

class TestFilterValidUrls:
    def test_empty_input_returns_empty(self):
        result = asyncio.run(_filter_valid_urls([]))
        assert result == []

    def test_all_valid_returns_unchanged(self):
        results = [
            {"title": "A", "url": "https://a.com/page", "snippet": "a"},
            {"title": "B", "url": "https://b.com/page", "snippet": "b"},
        ]

        async def fake_check_url(url, client):
            return url, True

        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.search.httpx.AsyncClient", return_value=mock_client_cm), \
                patch("app.services.search._check_url", new_callable=AsyncMock, side_effect=fake_check_url):
            filtered = asyncio.run(_filter_valid_urls(results))

        assert filtered == results

    def test_invalid_urls_dropped(self):
        results = [
            {"title": "A", "url": "https://a.com/page", "snippet": "a"},
            {"title": "B", "url": "https://b.com/missing", "snippet": "b"},
            {"title": "C", "url": "https://c.com/page", "snippet": "c"},
        ]

        async def fake_check_url(url, client):
            return url, url != "https://b.com/missing"

        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.search.httpx.AsyncClient", return_value=mock_client_cm), \
                patch("app.services.search._check_url", new_callable=AsyncMock, side_effect=fake_check_url):
            filtered = asyncio.run(_filter_valid_urls(results))

        assert filtered == [
            {"title": "A", "url": "https://a.com/page", "snippet": "a"},
            {"title": "C", "url": "https://c.com/page", "snippet": "c"},
        ]


# ── _build_search_context ────────────────────────────────────────────────────

class TestBuildSearchContext:
    def test_empty_results_returns_messages_unchanged(self):
        messages = [{"role": "user", "content": "What is gravity?"}]
        augmented, citations = _build_search_context(messages, [])

        assert augmented is messages
        assert citations == []

    def test_appends_citation_instruction_to_existing_system_message(self):
        messages = [
            {"role": "system", "content": "You are a tutor."},
            {"role": "user", "content": "What is gravity?"},
        ]
        results = [{"title": "Gravity - Wikipedia", "url": "https://en.wikipedia.org/wiki/Gravity", "snippet": "Gravity is a force."}]

        augmented, citations = _build_search_context(messages, results)

        system_msgs = [m for m in augmented if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0]["content"].startswith("You are a tutor.")
        assert "Cite sources" in system_msgs[0]["content"]

    def test_prepends_new_system_message_when_none_exists(self):
        messages = [{"role": "user", "content": "What is gravity?"}]
        results = [{"title": "Gravity - Wikipedia", "url": "https://en.wikipedia.org/wiki/Gravity", "snippet": "Gravity is a force."}]

        augmented, citations = _build_search_context(messages, results)

        assert augmented[0]["role"] == "system"
        assert "Cite sources" in augmented[0]["content"]
        # Original messages are still present after the new system message
        assert augmented[1]["role"] == "user"

    def test_last_user_message_gets_search_context_appended(self):
        messages = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Second question"},
        ]
        results = [{"title": "Result Title", "url": "https://example.com/page", "snippet": "Some snippet text"}]

        augmented, citations = _build_search_context(messages, results)

        last_user = next(m for m in reversed(augmented) if m["role"] == "user")
        assert last_user["content"].startswith("Second question")
        assert "Search results:" in last_user["content"]
        assert "[1] Result Title" in last_user["content"]
        assert "URL: https://example.com/page" in last_user["content"]
        assert "Some snippet text" in last_user["content"]

        # The earlier user message should be untouched
        first_user = next(m for m in augmented if m["role"] == "user")
        assert first_user["content"] == "First question"

    def test_citations_have_correct_shape_and_numbering(self):
        messages = [{"role": "user", "content": "Tell me about cells"}]
        results = [
            {"title": "Cell Biology", "url": "https://example.com/cells", "snippet": "About cells"},
            {"title": "Mitosis Overview", "url": "https://example.com/mitosis", "snippet": "About mitosis"},
        ]

        augmented, citations = _build_search_context(messages, results)

        assert citations == [
            {"n": 1, "title": "Cell Biology", "url": "https://example.com/cells"},
            {"n": 2, "title": "Mitosis Overview", "url": "https://example.com/mitosis"},
        ]


# ── _title_keywords ──────────────────────────────────────────────────────────

class TestTitleKeywords:
    def test_extracts_words_at_least_4_chars(self):
        keywords = _title_keywords("Cell Division and Mitosis")
        assert "Division" in keywords
        assert "Mitosis" in keywords
        # "and" is 3 chars and a stop word — excluded
        assert "and" not in keywords
        assert "Cell" in keywords  # exactly 4 chars, included

    def test_excludes_stop_words(self):
        keywords = _title_keywords("What is the Probability of Rolling a Die")
        lowered = [k.lower() for k in keywords]
        assert "what" not in lowered
        assert "the" not in lowered
        assert "is" not in lowered
        assert "probability" in lowered
        assert "rolling" in lowered

    def test_sorted_longest_first(self):
        keywords = _title_keywords("Photosynthesis and Cell Respiration")
        # "Photosynthesis" (14) > "Respiration" (11) > "Cell" (4)
        assert keywords[0] == "Photosynthesis"
        lengths = [len(k) for k in keywords]
        assert lengths == sorted(lengths, reverse=True)

    def test_splits_on_punctuation_and_dashes(self):
        keywords = _title_keywords("Mitosis: Phases - An Overview | Khan Academy")
        assert "Mitosis" in keywords
        assert "Phases" in keywords
        assert "Overview" in keywords
        assert "Khan" in keywords
        assert "Academy" in keywords
        # "An" is 2 chars — excluded
        assert "An" not in keywords


# ── _unlinked_search ──────────────────────────────────────────────────────────

class TestUnlinkedSearch:
    def test_finds_unlinked_term(self):
        text = "The probability of rolling a six is one sixth."
        match = _unlinked_search("probability", text)
        assert match is not None
        assert match.group(0).lower() == "probability"

    def test_does_not_match_term_already_inside_link(self):
        text = "The [probability](https://example.com) of rolling a six."
        match = _unlinked_search("probability", text)
        assert match is None

    def test_case_insensitive(self):
        text = "PROBABILITY is fun."
        match = _unlinked_search("probability", text)
        assert match is not None

    def test_no_match_returns_none(self):
        text = "This text has nothing relevant."
        match = _unlinked_search("probability", text)
        assert match is None


# ── _place_marker_inline ──────────────────────────────────────────────────────

class TestPlaceMarkerInline:
    def test_exact_phrase_match(self):
        before = "The probability of rolling a six is "
        after = " one sixth."
        result = _place_marker_inline("probability", "https://example.com/prob", before, after)

        assert "[probability](https://example.com/prob)" in result
        assert result.endswith(after)
        assert result.startswith("The ")

    def test_subphrase_fallback_when_exact_phrase_not_found(self):
        before = "Rolling a fair die gives equal outcomes for "
        after = "."
        # exact phrase "fair die outcomes" won't be found verbatim,
        # but a sub-phrase like "fair die" should match
        result = _place_marker_inline("fair die outcomes", "https://example.com/die", before, after)

        assert "(https://example.com/die)" in result
        assert result.endswith(after)

    def test_final_fallback_appends_phrase_link(self):
        before = "Some unrelated sentence "
        after = " continues here."
        result = _place_marker_inline("nonexistent phrase", "https://example.com/x", before, after)

        assert result == before + "[nonexistent phrase](https://example.com/x)" + after

    def test_formula_chars_skip_exact_match_and_use_fallback(self):
        before = "We solve the equation here "
        after = "."
        # phrase contains formula characters, so exact-match branch is skipped
        result = _place_marker_inline("x = y + 2", "https://example.com/eq", before, after)

        assert "(https://example.com/eq)" in result
        assert result.endswith(after)


# ── _inject_citation_links ────────────────────────────────────────────────────

class TestInjectCitationLinks:
    def test_phrase_marker_style_converted_to_inline_link(self):
        text = "The [probability][1] of rolling a six is one sixth."
        citations = [{"n": 1, "title": "Probability - Wikipedia", "url": "https://example.com/prob"}]

        result = _inject_citation_links(text, citations)

        assert "[probability](https://example.com/prob)" in result
        assert "[1]" not in result

    def test_bare_marker_converted_to_link(self):
        text = "Mitosis involves four phases [1]."
        citations = [{"n": 1, "title": "Mitosis Overview", "url": "https://example.com/mitosis"}]

        result = _inject_citation_links(text, citations)

        assert "[1](https://example.com/mitosis)" in result

    def test_no_marker_falls_back_to_keyword_match(self):
        text = "Mitosis is a process of cell division."
        citations = [{"n": 1, "title": "Mitosis Overview", "url": "https://example.com/mitosis"}]

        result = _inject_citation_links(text, citations)

        assert "(https://example.com/mitosis)" in result
        assert "[Mitosis]" in result or "[mitosis]" in result.lower()

    def test_leftover_phrase_marker_for_unknown_citation_stripped(self):
        text = "The [gravity][99] pulls objects down."
        citations = [{"n": 1, "title": "Probability", "url": "https://example.com/prob"}]

        result = _inject_citation_links(text, citations)

        assert "[99]" not in result
        assert "gravity" in result
        assert "[gravity]" not in result

    def test_leftover_bare_marker_for_unknown_citation_removed(self):
        text = "This fact is well known [99]."
        citations = [{"n": 1, "title": "Probability", "url": "https://example.com/prob"}]

        result = _inject_citation_links(text, citations)

        assert "[99]" not in result

    def test_multiple_citations_processed_independently(self):
        text = "[Mitosis][1] has [phases][2]."
        citations = [
            {"n": 1, "title": "Mitosis Overview", "url": "https://example.com/mitosis"},
            {"n": 2, "title": "Cell Phases", "url": "https://example.com/phases"},
        ]

        result = _inject_citation_links(text, citations)

        assert "(https://example.com/mitosis)" in result
        assert "(https://example.com/phases)" in result
        assert "[1]" not in result
        assert "[2]" not in result

    def test_no_citations_returns_text_with_no_bare_markers_stripped_when_absent(self):
        text = "Plain text with no markers."
        result = _inject_citation_links(text, [])
        assert result == "Plain text with no markers."


# ── get_chat_response_with_search ──────────────────────────────────────────────

def _make_chat_client(reply_content):
    fake_message = MagicMock()
    fake_message.content = reply_content
    fake_choice = MagicMock()
    fake_choice.message = fake_message
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=fake_response)
    return client


class TestGetChatResponseWithSearch:
    def test_returns_reply_and_empty_citations_without_db_links(self):
        client = _make_chat_client("Hello, here is your answer.")
        messages = [{"role": "user", "content": "What is gravity?"}]

        with patch("app.services.search._run_search", new_callable=AsyncMock, return_value=[]), \
                patch("app.services.search._filter_valid_urls", new_callable=AsyncMock, return_value=[]):
            result = asyncio.run(get_chat_response_with_search(client, "gpt-4", messages))

        assert result == {"reply": "Hello, here is your answer.", "citations": []}
        client.chat.completions.create.assert_awaited_once()

    def test_strips_whitespace_from_reply(self):
        client = _make_chat_client("   Padded reply.   ")
        messages = [{"role": "user", "content": "What is gravity?"}]

        with patch("app.services.search._run_search", new_callable=AsyncMock, return_value=[]), \
                patch("app.services.search._filter_valid_urls", new_callable=AsyncMock, return_value=[]):
            result = asyncio.run(get_chat_response_with_search(client, "gpt-4", messages))

        assert result["reply"] == "Padded reply."

    def test_db_links_produce_citations_and_inject_links(self):
        client = _make_chat_client("Mitosis involves [cell division][1].")
        messages = [{"role": "user", "content": "Explain mitosis."}]
        db_links = [
            {"title": "Mitosis Overview", "url": "https://example.com/mitosis", "description": "All about mitosis"},
        ]

        with patch("app.services.search._run_search", new_callable=AsyncMock, return_value=[]), \
                patch("app.services.search._filter_valid_urls", new_callable=AsyncMock, return_value=[]):
            result = asyncio.run(get_chat_response_with_search(client, "gpt-4", messages, db_links=db_links))

        assert result["citations"] == [
            {"n": 1, "title": "Mitosis Overview", "url": "https://example.com/mitosis"}
        ]
        assert "(https://example.com/mitosis)" in result["reply"]
        assert "[1]" not in result["reply"]

    def test_db_links_missing_url_are_filtered_out(self):
        client = _make_chat_client("Reply without citations.")
        messages = [{"role": "user", "content": "Explain mitosis."}]
        db_links = [
            {"title": "No URL link", "description": "Should be skipped"},
        ]

        with patch("app.services.search._run_search", new_callable=AsyncMock, return_value=[]), \
                patch("app.services.search._filter_valid_urls", new_callable=AsyncMock, return_value=[]):
            result = asyncio.run(get_chat_response_with_search(client, "gpt-4", messages, db_links=db_links))

        assert result["citations"] == []
        assert result["reply"] == "Reply without citations."

    def test_query_uses_last_user_message(self):
        client = _make_chat_client("Some reply.")
        messages = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Second question"},
        ]

        mock_run_search = AsyncMock(return_value=[])
        with patch("app.services.search._run_search", mock_run_search), \
                patch("app.services.search._filter_valid_urls", new_callable=AsyncMock, return_value=[]):
            asyncio.run(get_chat_response_with_search(client, "gpt-4", messages))

        mock_run_search.assert_awaited_once_with("Second question")

    def test_no_user_message_uses_empty_query(self):
        client = _make_chat_client("Some reply.")
        messages = [{"role": "system", "content": "You are a tutor."}]

        mock_run_search = AsyncMock(return_value=[])
        with patch("app.services.search._run_search", mock_run_search), \
                patch("app.services.search._filter_valid_urls", new_callable=AsyncMock, return_value=[]):
            asyncio.run(get_chat_response_with_search(client, "gpt-4", messages))

        mock_run_search.assert_awaited_once_with("")
