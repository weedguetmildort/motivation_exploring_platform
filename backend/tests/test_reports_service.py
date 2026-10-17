# backend/tests/test_reports_service.py
"""Unit tests for app.services.reports: CRUD + ownership-scoping backed by a mocked collection."""
from datetime import datetime, timezone
from unittest.mock import MagicMock
from bson import ObjectId
import pytest

from app.schemas.report import ReportCreate, ReportStatus, ReportCategory
from app.schemas.user import UserPublic
from app.services.reports import (
    get_reports_collection,
    ensure_indexes,
    create_report,
    list_reports,
    get_report,
    add_comment,
    update_status,
    _to_public,
)


@pytest.fixture
def user():
    return UserPublic(id="u1", email="student@test.edu", is_admin=False)


@pytest.fixture
def admin():
    return UserPublic(id="admin1", email="admin@test.edu", is_admin=True)


def make_report_doc(_id=None, **overrides):
    doc = {
        "_id": _id if _id is not None else ObjectId(),
        "user_id": "u1",
        "user_email": "student@test.edu",
        "quiz_id": "base",
        "question_id": "q1",
        "category": "bug",
        "description": "The submit button did nothing.",
        "status": "open",
        "comments": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    doc.update(overrides)
    return doc


class TestGetReportsCollection:
    def test_returns_reports_collection(self, mock_db, mock_col):
        result = get_reports_collection(mock_db)
        assert result is mock_col
        mock_db.__getitem__.assert_called_with("reports")


class TestEnsureIndexes:
    def test_creates_expected_indexes(self, mock_col):
        ensure_indexes(mock_col)
        mock_col.create_index.assert_any_call("user_id")
        mock_col.create_index.assert_any_call("status")
        mock_col.create_index.assert_any_call([("created_at", -1)])


class TestToPublic:
    def test_invalid_category_falls_back_to_other(self):
        doc = make_report_doc(category="not-a-real-category")
        pub = _to_public(doc)
        assert pub.category == ReportCategory.OTHER

    def test_invalid_status_falls_back_to_open(self):
        doc = make_report_doc(status="not-a-real-status")
        pub = _to_public(doc)
        assert pub.status == ReportStatus.OPEN

    def test_comments_converted(self):
        now = datetime.now(timezone.utc)
        doc = make_report_doc(comments=[
            {"id": "c1", "author_email": "admin@test.edu", "is_admin": True, "body": "Looking into it.", "created_at": now},
        ])
        pub = _to_public(doc)
        assert len(pub.comments) == 1
        assert pub.comments[0].author_email == "admin@test.edu"
        assert pub.comments[0].is_admin is True


class TestCreateReport:
    def test_stores_open_status_and_empty_comments(self, mock_col, user):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)
        data = ReportCreate(category=ReportCategory.BUG, description="  Broken choice  ", quiz_id="base", question_id="q1")

        result = create_report(mock_col, user, data)

        assert result.id == str(oid)
        assert result.status == ReportStatus.OPEN
        assert result.description == "Broken choice"
        assert result.comments == []

        inserted = mock_col.insert_one.call_args[0][0]
        assert inserted["category"] == "bug"
        assert inserted["status"] == "open"


class TestListReports:
    def test_no_filters_returns_all(self, mock_col):
        mock_col.find.return_value.sort.return_value = []
        list_reports(mock_col)
        mock_col.find.assert_called_once_with({})

    def test_user_id_and_status_scope_query(self, mock_col):
        mock_col.find.return_value.sort.return_value = []
        list_reports(mock_col, user_id="u1", status="open")
        mock_col.find.assert_called_once_with({"user_id": "u1", "status": "open"})


class TestGetReport:
    def test_invalid_object_id_returns_none(self, mock_col):
        assert get_report(mock_col, "not-an-oid") is None

    def test_found_without_user_id_scope(self, mock_col):
        oid = ObjectId()
        mock_col.find_one.return_value = make_report_doc(_id=oid)
        result = get_report(mock_col, str(oid))
        assert result is not None
        mock_col.find_one.assert_called_once_with({"_id": oid})

    def test_scoped_query_includes_user_id(self, mock_col):
        oid = ObjectId()
        mock_col.find_one.return_value = make_report_doc(_id=oid)
        get_report(mock_col, str(oid), user_id="u1")
        mock_col.find_one.assert_called_once_with({"_id": oid, "user_id": "u1"})

    def test_not_found_returns_none(self, mock_col):
        oid = ObjectId()
        mock_col.find_one.return_value = None
        assert get_report(mock_col, str(oid)) is None


class TestAddComment:
    def test_invalid_object_id_returns_none(self, mock_col, user):
        assert add_comment(mock_col, "not-an-oid", user, "body") is None

    def test_no_match_returns_none(self, mock_col, user):
        oid = ObjectId()
        mock_col.update_one.return_value = MagicMock(matched_count=0)
        assert add_comment(mock_col, str(oid), user, "body") is None

    def test_comment_pushed_with_author_and_admin_flag(self, mock_col, admin):
        oid = ObjectId()
        mock_col.update_one.return_value = MagicMock(matched_count=1)
        mock_col.find_one.return_value = make_report_doc(_id=oid)

        add_comment(mock_col, str(oid), admin, "  On it.  ")

        args = mock_col.update_one.call_args[0]
        assert args[0] == {"_id": oid}
        pushed = args[1]["$push"]["comments"]
        assert pushed["author_email"] == "admin@test.edu"
        assert pushed["is_admin"] is True
        assert pushed["body"] == "On it."

    def test_ownership_scoped_query_when_user_id_given(self, mock_col, user):
        oid = ObjectId()
        mock_col.update_one.return_value = MagicMock(matched_count=1)
        mock_col.find_one.return_value = make_report_doc(_id=oid)

        add_comment(mock_col, str(oid), user, "body", user_id="u1")

        args = mock_col.update_one.call_args[0]
        assert args[0] == {"_id": oid, "user_id": "u1"}


class TestUpdateStatus:
    def test_invalid_object_id_returns_none(self, mock_col):
        assert update_status(mock_col, "not-an-oid", ReportStatus.RESOLVED) is None

    def test_no_match_returns_none(self, mock_col):
        oid = ObjectId()
        mock_col.update_one.return_value = MagicMock(matched_count=0)
        assert update_status(mock_col, str(oid), ReportStatus.RESOLVED) is None

    def test_sets_status_value_not_enum(self, mock_col):
        oid = ObjectId()
        mock_col.update_one.return_value = MagicMock(matched_count=1)
        mock_col.find_one.return_value = make_report_doc(_id=oid, status="resolved")

        update_status(mock_col, str(oid), ReportStatus.RESOLVED)

        args = mock_col.update_one.call_args[0]
        assert args[1]["$set"]["status"] == "resolved"
