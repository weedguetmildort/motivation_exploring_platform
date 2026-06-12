# backend/tests/test_main.py
"""Tests for app/main.py: root/health routes, startup, and shutdown lifecycle."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.main import app, MONGO_DB


# ── Plain routes ─────────────────────────────────────────────────────────────

class TestPlainRoutes:
    def test_root_returns_hello_world(self):
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json() == {"message": "Hello world from FastAPI!"}

    def test_health_returns_ok(self):
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ── Helpers for building a mock Mongo client ────────────────────────────────

def _build_mock_mongo_client(missing_count=0):
    """Build a MagicMock MongoClient where db[key] always returns the same
    shared collection mock, configured so _startup() runs cleanly."""
    shared_col = MagicMock()
    shared_col.count_documents.return_value = missing_count
    # reload_knowledge_links_cache() and load_allowlist_cache() both iterate
    # the result of find() directly (no .sort() call during startup).
    shared_col.find.return_value = []

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=shared_col)

    client = MagicMock()
    client.admin.command.return_value = {"ok": 1}
    client.__getitem__ = MagicMock(return_value=mock_db)

    return client, mock_db, shared_col


# ── _startup ─────────────────────────────────────────────────────────────────

class TestStartup:
    def test_startup_sets_app_state_and_starts_scheduler(self):
        client, mock_db, shared_col = _build_mock_mongo_client(missing_count=0)

        with patch("app.main.MongoClient", return_value=client) as mock_mongo_client, \
             patch("app.scheduler.start_scheduler") as mock_start_scheduler:

            from app.main import _startup
            _startup()

        mock_mongo_client.assert_called_once()
        client.admin.command.assert_called_once_with("ping")

        assert app.state.mongo_client is client
        assert app.state.db is mock_db
        assert app.state.messages is shared_col
        assert app.state.knowledge_links == []
        assert app.state.allowlist_cache == set()

        mock_start_scheduler.assert_called_once_with(app)

    def test_startup_creates_indexes_on_messages(self):
        client, mock_db, shared_col = _build_mock_mongo_client(missing_count=0)

        with patch("app.main.MongoClient", return_value=client), \
             patch("app.scheduler.start_scheduler"):
            from app.main import _startup
            _startup()

        # messages.create_index called twice (conversation_id, created_at)
        assert shared_col.create_index.call_count >= 2

    def test_startup_runs_migration_when_missing_status_docs(self):
        client, mock_db, shared_col = _build_mock_mongo_client(missing_count=5)

        with patch("app.main.MongoClient", return_value=client), \
             patch("app.scheduler.start_scheduler"):
            from app.main import _startup
            _startup()

        # update_many should be called 3 times for the migration branch
        assert shared_col.update_many.call_count == 3

    def test_startup_skips_migration_when_no_missing_status_docs(self):
        client, mock_db, shared_col = _build_mock_mongo_client(missing_count=0)

        with patch("app.main.MongoClient", return_value=client), \
             patch("app.scheduler.start_scheduler"):
            from app.main import _startup
            _startup()

        shared_col.update_many.assert_not_called()

    def test_startup_reraises_server_selection_timeout(self):
        client = MagicMock()
        client.admin.command.side_effect = ServerSelectionTimeoutError("no servers")

        with patch("app.main.MongoClient", return_value=client), \
             patch("app.scheduler.start_scheduler"):
            from app.main import _startup
            with pytest.raises(ServerSelectionTimeoutError):
                _startup()

    def test_startup_uses_configured_mongo_db_name(self):
        client, mock_db, shared_col = _build_mock_mongo_client(missing_count=0)

        with patch("app.main.MongoClient", return_value=client), \
             patch("app.scheduler.start_scheduler"):
            from app.main import _startup
            _startup()

        client.__getitem__.assert_called_with(MONGO_DB)


# ── _shutdown ────────────────────────────────────────────────────────────────

class TestShutdown:
    def test_shutdown_stops_scheduler_and_closes_client(self):
        from app.main import _shutdown

        mongo_client = MagicMock()
        app.state.mongo_client = mongo_client

        with patch("app.scheduler.stop_scheduler") as mock_stop_scheduler:
            _shutdown()

        mock_stop_scheduler.assert_called_once()
        mongo_client.close.assert_called_once()

    def test_shutdown_handles_missing_mongo_client(self):
        from app.main import _shutdown

        if hasattr(app.state, "mongo_client"):
            del app.state.mongo_client

        with patch("app.scheduler.stop_scheduler") as mock_stop_scheduler:
            # Should not raise even though app.state.mongo_client doesn't exist
            _shutdown()

        mock_stop_scheduler.assert_called_once()
