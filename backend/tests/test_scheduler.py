# backend/tests/test_scheduler.py
"""Tests for app/scheduler.py: start/stop lifecycle and run_jobs_now."""

import types
from unittest.mock import MagicMock, patch

import pytest

from app import scheduler


@pytest.fixture(autouse=True)
def _ensure_scheduler_stopped():
    """Safety net: make sure no background scheduler leaks between tests."""
    yield
    scheduler.stop_scheduler()


def _make_app(interval_hours=12):
    return types.SimpleNamespace(
        state=types.SimpleNamespace(
            settings=types.SimpleNamespace(LINK_CHECK_INTERVAL_HOURS=interval_hours)
        )
    )


# ── start_scheduler / stop_scheduler ────────────────────────────────────────

class TestStartStopScheduler:
    def test_start_scheduler_starts_background_scheduler(self):
        app = _make_app(interval_hours=12)
        try:
            scheduler.start_scheduler(app)
            assert scheduler._scheduler is not None
            assert scheduler._scheduler.running
        finally:
            scheduler.stop_scheduler()

    def test_start_scheduler_idempotent_when_already_running(self):
        app = _make_app(interval_hours=12)
        try:
            scheduler.start_scheduler(app)
            first_instance = scheduler._scheduler
            assert first_instance.running

            # Calling again should return early without replacing the instance
            scheduler.start_scheduler(app)
            assert scheduler._scheduler is first_instance
            assert scheduler._scheduler.running
        finally:
            scheduler.stop_scheduler()

    def test_stop_scheduler_clears_module_state(self):
        app = _make_app(interval_hours=12)
        scheduler.start_scheduler(app)
        assert scheduler._scheduler is not None

        scheduler.stop_scheduler()

        assert scheduler._scheduler is None

    def test_stop_scheduler_when_nothing_running_is_noop(self):
        # Ensure clean state first
        scheduler.stop_scheduler()
        assert scheduler._scheduler is None

        # Calling again should not raise
        scheduler.stop_scheduler()
        assert scheduler._scheduler is None


# ── run_jobs_now ─────────────────────────────────────────────────────────────

class TestRunJobsNow:
    def test_run_jobs_now_calls_health_discovery_and_reloads_cache(self):
        app = types.SimpleNamespace(
            state=types.SimpleNamespace(
                db=MagicMock(),
                settings=MagicMock(),
                knowledge_links=[],
            )
        )

        fake_links = [{"id": "1", "title": "T", "url": "https://x.com", "description": "d"}]

        with patch("app.services.link_health.run_health_check", return_value={"checked": 0}) as mock_health, \
             patch("app.services.link_health.run_discovery", return_value={"checked": 0}) as mock_discovery, \
             patch("app.services.allowlist.get_allowlist_collection", return_value=MagicMock()) as mock_get_allowlist_col, \
             patch("app.services.allowlist.load_allowlist_cache", return_value=set()) as mock_load_allowlist, \
             patch("app.services.knowledge_links.get_knowledge_links_collection", return_value=MagicMock()) as mock_get_links_col, \
             patch("app.services.knowledge_links.reload_knowledge_links_cache", return_value=fake_links) as mock_reload_cache:

            scheduler.run_jobs_now(app)

        mock_get_allowlist_col.assert_called_once_with(app.state.db)
        mock_load_allowlist.assert_called_once()
        mock_health.assert_called_once()
        mock_discovery.assert_called_once()
        mock_get_links_col.assert_called_once_with(app.state.db)
        mock_reload_cache.assert_called_once()

        assert app.state.knowledge_links == fake_links

    def test_run_jobs_now_passes_allowlist_cache_to_health_and_discovery(self):
        app = types.SimpleNamespace(
            state=types.SimpleNamespace(
                db=MagicMock(),
                settings=MagicMock(),
                knowledge_links=[],
            )
        )

        allowlist_cache = {"khanacademy.org"}

        with patch("app.services.link_health.run_health_check", return_value={"checked": 1}) as mock_health, \
             patch("app.services.link_health.run_discovery", return_value={"found": 2}) as mock_discovery, \
             patch("app.services.allowlist.get_allowlist_collection", return_value=MagicMock()), \
             patch("app.services.allowlist.load_allowlist_cache", return_value=allowlist_cache), \
             patch("app.services.knowledge_links.get_knowledge_links_collection", return_value=MagicMock()), \
             patch("app.services.knowledge_links.reload_knowledge_links_cache", return_value=[]):

            scheduler.run_jobs_now(app)

        # Both health check and discovery should receive the loaded allowlist cache
        health_args = mock_health.call_args[0]
        discovery_args = mock_discovery.call_args[0]
        assert allowlist_cache in health_args
        assert allowlist_cache in discovery_args
