# backend/tests/test_allowlist_service.py
"""Unit tests for the allowlist service: domain normalization, subdomain matching, and CRUD."""
from datetime import datetime, timezone
from unittest.mock import MagicMock
from bson import ObjectId
import pytest
from pymongo.errors import DuplicateKeyError

from app.services.allowlist import (
    _extract_registrable_domain,
    _normalize_domain,
    domain_is_allowed,
    load_allowlist_cache,
    add_domain,
    remove_domain,
    list_domains,
)


# ── _extract_registrable_domain ──────────────────────────────────────────────

class TestExtractRegistrableDomain:
    def test_simple_url(self):
        assert _extract_registrable_domain("https://khanacademy.org/math") == "khanacademy.org"

    def test_strips_www(self):
        assert _extract_registrable_domain("http://www.wikipedia.org/wiki/Probability") == "wikipedia.org"

    def test_subdomain_returns_registrable_part(self):
        # cs.stanford.edu → last two parts → stanford.edu
        assert _extract_registrable_domain("https://cs.stanford.edu/courses/intro") == "stanford.edu"

    def test_bare_domain_no_scheme(self):
        assert _extract_registrable_domain("khanacademy.org") == "khanacademy.org"

    def test_bare_domain_with_www(self):
        assert _extract_registrable_domain("www.example.com") == "example.com"

    def test_strips_path_and_query(self):
        assert _extract_registrable_domain("https://example.com/a/b/c?x=1#frag") == "example.com"

    def test_strips_port(self):
        assert _extract_registrable_domain("https://localhost:8000/api") == "localhost"

    def test_empty_string_returns_none(self):
        assert _extract_registrable_domain("") is None


# ── _normalize_domain ─────────────────────────────────────────────────────────

class TestNormalizeDomain:
    def test_full_url_normalized(self):
        assert _normalize_domain("https://khanacademy.org/path?q=1") == "khanacademy.org"

    def test_strips_www(self):
        assert _normalize_domain("www.stanford.edu") == "stanford.edu"

    def test_lowercases(self):
        assert _normalize_domain("KHANACADEMY.ORG") == "khanacademy.org"

    def test_invalid_domain_raises(self):
        with pytest.raises(ValueError):
            _normalize_domain("not a domain")

    def test_single_label_raises(self):
        # "localhost" has no dot → invalid per regex
        with pytest.raises(ValueError):
            _normalize_domain("localhost")


# ── domain_is_allowed ────────────────────────────────────────────────────────

class TestDomainIsAllowed:
    def test_exact_match(self):
        assert domain_is_allowed("https://khanacademy.org/page", {"khanacademy.org"})

    def test_subdomain_passes_when_registrable_listed(self):
        # cs.stanford.edu registrable part → stanford.edu
        assert domain_is_allowed("https://cs.stanford.edu/courses", {"stanford.edu"})

    def test_deep_subdomain_passes(self):
        assert domain_is_allowed("https://a.b.example.com/path", {"example.com"})

    def test_unlisted_domain_blocked(self):
        assert not domain_is_allowed("https://shady-site.net/prob", {"khanacademy.org"})

    def test_empty_allowlist_blocks_all(self):
        assert not domain_is_allowed("https://khanacademy.org/page", set())

    def test_garbage_url_blocked(self):
        assert not domain_is_allowed("not-a-url", {"khanacademy.org"})


# ── load_allowlist_cache ─────────────────────────────────────────────────────

class TestLoadAllowlistCache:
    def test_returns_set_of_domains(self):
        col = MagicMock()
        col.find.return_value = [
            {"domain": "khanacademy.org"},
            {"domain": "stanford.edu"},
        ]
        result = load_allowlist_cache(col)
        assert result == {"khanacademy.org", "stanford.edu"}

    def test_empty_collection_returns_empty_set(self):
        col = MagicMock()
        col.find.return_value = []
        assert load_allowlist_cache(col) == set()


# ── add_domain ────────────────────────────────────────────────────────────────

class TestAddDomain:
    def test_successful_add(self):
        col = MagicMock()
        oid = ObjectId()
        col.insert_one.return_value = MagicMock(inserted_id=oid)

        entry = add_domain(col, "https://khanacademy.org/math", added_by="admin@test.edu")

        assert entry.domain == "khanacademy.org"
        assert entry.added_by == "admin@test.edu"
        assert str(entry.id) == str(oid)

    def test_strips_scheme_and_path(self):
        col = MagicMock()
        col.insert_one.return_value = MagicMock(inserted_id=ObjectId())

        entry = add_domain(col, "https://www.stanford.edu/courses/intro", "admin@test.edu")
        assert entry.domain == "stanford.edu"

    def test_duplicate_raises(self):
        col = MagicMock()
        col.insert_one.side_effect = DuplicateKeyError("dup key")

        with pytest.raises(DuplicateKeyError):
            add_domain(col, "khanacademy.org", "admin@test.edu")

    def test_invalid_domain_raises_value_error(self):
        col = MagicMock()
        with pytest.raises(ValueError):
            add_domain(col, "not a domain!!!", "admin@test.edu")


# ── remove_domain ─────────────────────────────────────────────────────────────

class TestRemoveDomain:
    def test_removes_existing_domain(self):
        oid = ObjectId()
        col = MagicMock()
        col.find_one.return_value = {
            "_id": oid, "domain": "khanacademy.org",
            "added_by": "admin@test.edu", "added_at": datetime.now(timezone.utc),
        }

        result = remove_domain(col, str(oid))

        col.delete_one.assert_called_once_with({"_id": oid})
        assert result.domain == "khanacademy.org"

    def test_returns_none_for_invalid_id(self):
        col = MagicMock()
        assert remove_domain(col, "not-an-objectid") is None
        col.find_one.assert_not_called()

    def test_returns_none_when_not_found(self):
        col = MagicMock()
        col.find_one.return_value = None
        assert remove_domain(col, str(ObjectId())) is None


# ── list_domains ──────────────────────────────────────────────────────────────

class TestListDomains:
    def test_returns_sorted_entries(self):
        now = datetime.now(timezone.utc)
        col = MagicMock()
        col.find.return_value.sort.return_value = [
            {"_id": ObjectId(), "domain": "khanacademy.org", "added_by": "a@b.com", "added_at": now},
            {"_id": ObjectId(), "domain": "stanford.edu", "added_by": "a@b.com", "added_at": now},
        ]

        results = list_domains(col)
        assert len(results) == 2
        assert results[0].domain == "khanacademy.org"
        assert results[1].domain == "stanford.edu"
