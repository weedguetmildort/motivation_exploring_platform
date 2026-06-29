# backend/tests/test_copy_events_service.py
"""Unit tests for app.services.copy_events: CRUD backed by a mocked collection."""
from unittest.mock import MagicMock
from bson import ObjectId
import pytest

from app.schemas.copy_event import CopyEventCreate
from app.schemas.user import UserPublic
from app.services.copy_events import (
    get_copy_events_collection,
    ensure_indexes,
    create_copy_event,
    list_copy_events,
)


@pytest.fixture
def user():
    return UserPublic(id="u1", email="student@test.edu", is_admin=False)


class TestGetCopyEventsCollection:
    def test_returns_copy_events_collection(self, mock_db, mock_col):
        result = get_copy_events_collection(mock_db)
        assert result is mock_col
        mock_db.__getitem__.assert_called_with("copy_events")


class TestEnsureIndexes:
    def test_creates_expected_indexes(self, mock_col):
        ensure_indexes(mock_col)
        mock_col.create_index.assert_any_call("user_id")
        mock_col.create_index.assert_any_call("conversation_id")
        mock_col.create_index.assert_any_call([("created_at", -1)])


class TestCreateCopyEvent:
    def test_stores_all_fields(self, mock_col, user):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)
        data = CopyEventCreate(
            quiz_id="base", question_id="q1", conversation_id="conv1",
            copied_text="The probability is 1/6.",
        )

        result = create_copy_event(mock_col, user, data)

        assert result.id == str(oid)
        assert result.user_id == "u1"
        assert result.user_email == "student@test.edu"
        assert result.copied_text == "The probability is 1/6."
        assert result.created_at is not None

    def test_optional_fields_default_to_none(self, mock_col, user):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)
        data = CopyEventCreate(copied_text="some text")

        result = create_copy_event(mock_col, user, data)

        assert result.quiz_id is None
        assert result.question_id is None
        assert result.conversation_id is None


class TestListCopyEvents:
    def test_no_user_id_returns_all(self, mock_col):
        mock_col.find.return_value.sort.return_value = []
        list_copy_events(mock_col)
        mock_col.find.assert_called_once_with({})

    def test_user_id_scopes_query(self, mock_col):
        mock_col.find.return_value.sort.return_value = []
        list_copy_events(mock_col, user_id="u1")
        mock_col.find.assert_called_once_with({"user_id": "u1"})
