# backend/tests/test_link_clicks_service.py
"""Unit tests for app.services.link_clicks: CRUD backed by a mocked collection."""
from unittest.mock import MagicMock
from bson import ObjectId
import pytest

from app.schemas.link_click import LinkClickCreate
from app.schemas.user import UserPublic
from app.services.link_clicks import (
    get_link_clicks_collection,
    ensure_indexes,
    create_link_click,
    list_link_clicks,
)


@pytest.fixture
def user():
    return UserPublic(id="u1", email="student@test.edu", is_admin=False)


class TestGetLinkClicksCollection:
    def test_returns_link_clicks_collection(self, mock_db, mock_col):
        result = get_link_clicks_collection(mock_db)
        assert result is mock_col
        mock_db.__getitem__.assert_called_with("link_clicks")


class TestEnsureIndexes:
    def test_creates_expected_indexes(self, mock_col):
        ensure_indexes(mock_col)
        mock_col.create_index.assert_any_call("user_id")
        mock_col.create_index.assert_any_call("conversation_id")
        mock_col.create_index.assert_any_call([("clicked_at", -1)])


class TestCreateLinkClick:
    def test_stores_all_fields(self, mock_col, user):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)
        data = LinkClickCreate(
            quiz_id="links", question_id="q1", conversation_id="conv1",
            url="https://example.com/article",
        )

        result = create_link_click(mock_col, user, data)

        assert result.id == str(oid)
        assert result.user_id == "u1"
        assert result.user_email == "student@test.edu"
        assert result.quiz_id == "links"
        assert result.question_id == "q1"
        assert result.conversation_id == "conv1"
        assert result.url == "https://example.com/article"
        assert result.clicked_at is not None

        inserted = mock_col.insert_one.call_args[0][0]
        assert inserted["user_id"] == "u1"
        assert inserted["url"] == "https://example.com/article"

    def test_optional_fields_default_to_none(self, mock_col, user):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)
        data = LinkClickCreate(url="https://example.com")

        result = create_link_click(mock_col, user, data)

        assert result.quiz_id is None
        assert result.question_id is None
        assert result.conversation_id is None


class TestListLinkClicks:
    def test_no_user_id_returns_all(self, mock_col):
        mock_col.find.return_value.sort.return_value = []
        list_link_clicks(mock_col)
        mock_col.find.assert_called_once_with({})

    def test_user_id_scopes_query(self, mock_col):
        mock_col.find.return_value.sort.return_value = []
        list_link_clicks(mock_col, user_id="u1")
        mock_col.find.assert_called_once_with({"user_id": "u1"})
