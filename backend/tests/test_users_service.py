# backend/tests/test_users_service.py
"""Unit tests for app.services.users: user CRUD/lookup helpers backed by a mocked collection."""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.security import hash_password
from app.schemas.user import AssignedVar, SurveyStage
from app.services.users import (
    get_users_collection,
    ensure_indexes,
    create_user,
    find_user_by_email,
    check_user_password,
    maybe_touch_last_active,
    _next_assigned_var,
    _normalize_stage,
    _to_public,
)


# ── get_users_collection ─────────────────────────────────────────────────────

class TestGetUsersCollection:
    def test_returns_users_collection_from_db(self, mock_db, mock_col):
        result = get_users_collection(mock_db)
        assert result is mock_col
        mock_db.__getitem__.assert_called_with("users")


# ── ensure_indexes ────────────────────────────────────────────────────────────

class TestEnsureIndexes:
    def test_creates_unique_email_index(self, mock_col):
        ensure_indexes(mock_col)
        mock_col.create_index.assert_called_once_with("email", unique=True)


# ── _normalize_stage ──────────────────────────────────────────────────────────

class TestNormalizeStage:
    def test_returns_enum_as_is(self):
        assert _normalize_stage(SurveyStage.complete) == SurveyStage.complete

    def test_valid_string_converted(self):
        assert _normalize_stage("post_base") == SurveyStage.post_base

    def test_invalid_string_falls_back_to_pre_base(self):
        assert _normalize_stage("not_a_stage") == SurveyStage.pre_base

    def test_none_falls_back_to_pre_base(self):
        assert _normalize_stage(None) == SurveyStage.pre_base

    def test_other_type_falls_back_to_pre_base(self):
        assert _normalize_stage(123) == SurveyStage.pre_base


# ── _to_public ────────────────────────────────────────────────────────────────

class TestToPublic:
    def test_minimal_doc(self):
        oid = ObjectId()
        doc = {"_id": oid, "email": "user@test.edu"}
        pub = _to_public(doc)

        assert pub.id == str(oid)
        assert pub.email == "user@test.edu"
        assert pub.first_name is None
        assert pub.last_name is None
        assert pub.consent is None
        assert pub.assigned_var == AssignedVar.followup
        assert pub.is_admin is False
        assert pub.demographics_completed is False
        assert pub.survey_stage == SurveyStage.pre_base

    def test_full_doc(self):
        oid = ObjectId()
        now = datetime.now(timezone.utc)
        doc = {
            "_id": oid,
            "email": "user@test.edu",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "consent": True,
            "consent_given_at": now,
            "assigned_var": AssignedVar.double.value,
            "is_admin": True,
            "demographics_completed": True,
            "survey_pre_base_completed": True,
            "quiz_base_completed": True,
            "survey_post_base_completed": True,
            "quiz_variant_completed": True,
            "survey_post_variant_completed": True,
            "survey_stage": "post_variant",
        }
        pub = _to_public(doc)

        assert pub.first_name == "Ada"
        assert pub.last_name == "Lovelace"
        assert pub.consent is True
        assert pub.assigned_var == AssignedVar.double
        assert pub.is_admin is True
        assert pub.demographics_completed is True
        assert pub.survey_stage == SurveyStage.post_variant

    def test_invalid_stage_falls_back(self):
        oid = ObjectId()
        doc = {"_id": oid, "email": "user@test.edu", "survey_stage": "garbage"}
        pub = _to_public(doc)
        assert pub.survey_stage == SurveyStage.pre_base


# ── _next_assigned_var ────────────────────────────────────────────────────────

class TestNextAssignedVar:
    def _set_seq(self, mock_col, seq):
        counters = mock_col.database["counters"]
        counters.find_one_and_update.return_value = {"_id": "user_signup_round_robin", "seq": seq}
        return counters

    def test_seq_1_returns_followup(self, mock_col):
        self._set_seq(mock_col, 1)
        assert _next_assigned_var(mock_col) == AssignedVar.followup.value

    def test_seq_2_returns_double(self, mock_col):
        self._set_seq(mock_col, 2)
        assert _next_assigned_var(mock_col) == AssignedVar.double.value

    def test_seq_3_returns_links(self, mock_col):
        self._set_seq(mock_col, 3)
        assert _next_assigned_var(mock_col) == AssignedVar.links.value

    def test_seq_4_wraps_to_followup(self, mock_col):
        self._set_seq(mock_col, 4)
        assert _next_assigned_var(mock_col) == AssignedVar.followup.value

    def test_uses_upsert_and_increment(self, mock_col):
        counters = self._set_seq(mock_col, 1)
        _next_assigned_var(mock_col)
        args, kwargs = counters.find_one_and_update.call_args
        assert args[0] == {"_id": "user_signup_round_robin"}
        assert args[1] == {"$inc": {"seq": 1}}
        assert kwargs["upsert"] is True


# ── create_user ───────────────────────────────────────────────────────────────

class TestCreateUser:
    def test_successful_creation(self, mock_col):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)
        counters = mock_col.database["counters"]
        counters.find_one_and_update.return_value = {"_id": "user_signup_round_robin", "seq": 1}

        result = create_user(
            mock_col,
            email="  User@Example.com  ",
            password="plainpassword",
            first_name="  Ada ",
            last_name=" Lovelace ",
            consent=True,
        )

        assert result.id == str(oid)
        assert result.email == "user@example.com"
        assert result.first_name == "Ada"
        assert result.last_name == "Lovelace"
        assert result.assigned_var == AssignedVar.followup
        assert result.is_admin is False
        assert result.survey_stage == SurveyStage.pre_base

        # insert_one called with the right shape
        inserted_doc = mock_col.insert_one.call_args[0][0]
        assert inserted_doc["email"] == "user@example.com"
        assert inserted_doc["first_name"] == "Ada"
        assert inserted_doc["last_name"] == "Lovelace"
        assert inserted_doc["consent"] is True
        assert inserted_doc["password_hash"] != "plainpassword"
        assert inserted_doc["is_admin"] is False
        assert inserted_doc["survey_stage"] == SurveyStage.pre_base.value

        # assigned_var update_one called with the round-robin result
        mock_col.update_one.assert_called_once_with(
            {"_id": oid}, {"$set": {"assigned_var": AssignedVar.followup.value}}
        )

    def test_password_is_hashed(self, mock_col):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)
        counters = mock_col.database["counters"]
        counters.find_one_and_update.return_value = {"_id": "user_signup_round_robin", "seq": 1}

        create_user(
            mock_col,
            email="user@example.com",
            password="supersecret",
            first_name="A",
            last_name="B",
            consent=True,
        )

        inserted_doc = mock_col.insert_one.call_args[0][0]
        assert inserted_doc["password_hash"].startswith("$argon2")

    def test_consent_not_true_raises_value_error(self, mock_col):
        with pytest.raises(ValueError):
            create_user(
                mock_col,
                email="user@example.com",
                password="plainpassword",
                first_name="A",
                last_name="B",
                consent=False,
            )
        mock_col.insert_one.assert_not_called()

    def test_duplicate_email_raises(self, mock_col):
        mock_col.insert_one.side_effect = DuplicateKeyError("E11000 duplicate key error")

        with pytest.raises(DuplicateKeyError):
            create_user(
                mock_col,
                email="dup@example.com",
                password="plainpassword",
                first_name="A",
                last_name="B",
                consent=True,
            )


# ── find_user_by_email ────────────────────────────────────────────────────────

class TestFindUserByEmail:
    def test_found(self, mock_col):
        doc = {"_id": ObjectId(), "email": "user@example.com", "password_hash": "hash"}
        mock_col.find_one.return_value = doc

        result = find_user_by_email(mock_col, "user@example.com")

        assert result == doc
        mock_col.find_one.assert_called_once_with({"email": "user@example.com"})

    def test_lowercases_email_for_lookup(self, mock_col):
        mock_col.find_one.return_value = None
        find_user_by_email(mock_col, "USER@Example.COM")
        mock_col.find_one.assert_called_once_with({"email": "user@example.com"})

    def test_not_found_returns_none(self, mock_col):
        mock_col.find_one.return_value = None
        result = find_user_by_email(mock_col, "nobody@example.com")
        assert result is None


# ── check_user_password ───────────────────────────────────────────────────────

class TestCheckUserPassword:
    def test_correct_password_returns_true(self):
        user_doc = {"password_hash": hash_password("correct-password")}
        assert check_user_password(user_doc, "correct-password") is True

    def test_wrong_password_returns_false(self):
        user_doc = {"password_hash": hash_password("correct-password")}
        assert check_user_password(user_doc, "wrong-password") is False


# ── maybe_touch_last_active ──────────────────────────────────────────────────

class TestMaybeTouchLastActive:
    def test_missing_last_active_at_updates(self, mock_col):
        oid = ObjectId()
        doc = {"_id": oid}

        maybe_touch_last_active(mock_col, doc)

        mock_col.update_one.assert_called_once()
        args = mock_col.update_one.call_args[0]
        assert args[0] == {"_id": oid}
        assert "last_active_at" in args[1]["$set"]

    def test_recent_value_does_not_update(self, mock_col):
        oid = ObjectId()
        doc = {"_id": oid, "last_active_at": datetime.now(timezone.utc) - timedelta(seconds=5)}

        maybe_touch_last_active(mock_col, doc)

        mock_col.update_one.assert_not_called()

    def test_stale_value_updates(self, mock_col):
        oid = ObjectId()
        doc = {"_id": oid, "last_active_at": datetime.now(timezone.utc) - timedelta(minutes=10)}

        maybe_touch_last_active(mock_col, doc)

        mock_col.update_one.assert_called_once()

    def test_naive_datetime_from_mongo_round_trip_does_not_raise(self, mock_col):
        """pymongo returns stored datetimes as naive UTC by default. A recent
        naive value must be treated as recent, not raise on subtraction."""
        oid = ObjectId()
        naive_recent = datetime.utcnow() - timedelta(seconds=5)
        assert naive_recent.tzinfo is None
        doc = {"_id": oid, "last_active_at": naive_recent}

        maybe_touch_last_active(mock_col, doc)  # must not raise

        mock_col.update_one.assert_not_called()

    def test_naive_stale_datetime_updates(self, mock_col):
        oid = ObjectId()
        naive_stale = datetime.utcnow() - timedelta(minutes=10)
        doc = {"_id": oid, "last_active_at": naive_stale}

        maybe_touch_last_active(mock_col, doc)

        mock_col.update_one.assert_called_once()
