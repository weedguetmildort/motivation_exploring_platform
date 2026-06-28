# backend/tests/test_auth_api.py
"""FastAPI TestClient integration tests for app.api.auth (signup, login, me, logout, change-password)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.api.auth import router as auth_router, get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.schemas.user import AssignedVar, SurveyStage, UserPublic


# ── Local app/fixtures (do not touch conftest.py) ────────────────────────────

@pytest.fixture
def auth_mock_col():
    return MagicMock()


@pytest.fixture
def auth_mock_db(auth_mock_col):
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=auth_mock_col)
    return db


@pytest.fixture
def auth_app(auth_mock_db):
    app = FastAPI()
    app.include_router(auth_router)
    app.state.db = auth_mock_db
    return app


@pytest.fixture
def auth_client(auth_app):
    return TestClient(auth_app)


@pytest.fixture
def overridden_app(auth_mock_db, regular_user):
    """Auth app with get_current_user overridden to a fixed regular_user."""
    app = FastAPI()
    app.include_router(auth_router)
    app.state.db = auth_mock_db
    app.dependency_overrides[get_current_user] = lambda: regular_user
    return app


@pytest.fixture
def overridden_client(overridden_app):
    return TestClient(overridden_app)


def make_user_doc(email="student@test.edu", password="correct-password", **overrides):
    doc = {
        "_id": ObjectId(),
        "email": email,
        "password_hash": hash_password(password),
        "first_name": "Ada",
        "last_name": "Lovelace",
        "consent": True,
        "consent_given_at": datetime.now(timezone.utc),
        "assigned_var": AssignedVar.followup.value,
        "is_admin": False,
        "demographics_completed": False,
        "survey_pre_base_completed": False,
        "quiz_base_completed": False,
        "survey_post_base_completed": False,
        "quiz_variant_completed": False,
        "survey_post_variant_completed": False,
        "survey_stage": SurveyStage.pre_base.value,
    }
    doc.update(overrides)
    return doc


VALID_SIGNUP_PAYLOAD = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "newuser@example.com",
    "password": "plainpassword",
    "consent": True,
}


# ═══════════════════════════════════════════════════════════════════════════
# POST /auth/signup
# ═══════════════════════════════════════════════════════════════════════════

class TestSignup:
    def test_successful_signup(self, auth_client, auth_mock_col):
        oid = ObjectId()
        auth_mock_col.insert_one.return_value = MagicMock(inserted_id=oid)
        auth_mock_col.database.__getitem__.return_value.find_one_and_update.return_value = {
            "_id": "user_signup_round_robin", "seq": 1
        }

        resp = auth_client.post("/auth/signup", json=VALID_SIGNUP_PAYLOAD)

        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["first_name"] == "Ada"
        assert data["user"]["last_name"] == "Lovelace"
        assert data["user"]["id"] == str(oid)

        # Session cookie set
        settings = get_settings()
        assert settings.COOKIE_NAME in resp.cookies

    def test_ensure_indexes_called(self, auth_client, auth_mock_col):
        oid = ObjectId()
        auth_mock_col.insert_one.return_value = MagicMock(inserted_id=oid)
        auth_mock_col.database.__getitem__.return_value.find_one_and_update.return_value = {
            "_id": "user_signup_round_robin", "seq": 1
        }

        auth_client.post("/auth/signup", json=VALID_SIGNUP_PAYLOAD)

        auth_mock_col.create_index.assert_called_with("email", unique=True)

    def test_missing_field_returns_422(self, auth_client):
        payload = {k: v for k, v in VALID_SIGNUP_PAYLOAD.items() if k != "email"}
        resp = auth_client.post("/auth/signup", json=payload)
        assert resp.status_code == 422

    def test_invalid_email_returns_422(self, auth_client):
        payload = {**VALID_SIGNUP_PAYLOAD, "email": "not-an-email"}
        resp = auth_client.post("/auth/signup", json=payload)
        assert resp.status_code == 422

    def test_weak_password_returns_422(self, auth_client):
        payload = {**VALID_SIGNUP_PAYLOAD, "password": "abc"}
        resp = auth_client.post("/auth/signup", json=payload)
        assert resp.status_code == 422

    def test_consent_false_returns_400(self, auth_client, auth_mock_col):
        payload = {**VALID_SIGNUP_PAYLOAD, "consent": False}
        resp = auth_client.post("/auth/signup", json=payload)

        assert resp.status_code == 400
        assert "consent" in resp.json()["detail"].lower()
        auth_mock_col.insert_one.assert_not_called()

    def test_duplicate_email_returns_400(self, auth_client, auth_mock_col):
        auth_mock_col.insert_one.side_effect = DuplicateKeyError("E11000 duplicate key error")

        resp = auth_client.post("/auth/signup", json=VALID_SIGNUP_PAYLOAD)

        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# POST /auth/login
# ═══════════════════════════════════════════════════════════════════════════

class TestLogin:
    def test_successful_login_sets_cookie(self, auth_client, auth_mock_col):
        doc = make_user_doc(email="student@test.edu", password="correct-password")
        auth_mock_col.find_one.return_value = doc

        resp = auth_client.post("/auth/login", json={
            "email": "student@test.edu",
            "password": "correct-password",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["email"] == "student@test.edu"

        settings = get_settings()
        assert settings.COOKIE_NAME in resp.cookies

    def test_wrong_password_returns_401(self, auth_client, auth_mock_col):
        doc = make_user_doc(email="student@test.edu", password="correct-password")
        auth_mock_col.find_one.return_value = doc

        resp = auth_client.post("/auth/login", json={
            "email": "student@test.edu",
            "password": "wrong-password",
        })

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    def test_nonexistent_user_returns_401(self, auth_client, auth_mock_col):
        auth_mock_col.find_one.return_value = None

        resp = auth_client.post("/auth/login", json={
            "email": "nobody@example.com",
            "password": "whatever",
        })

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"


# ═══════════════════════════════════════════════════════════════════════════
# GET /auth/me
# ═══════════════════════════════════════════════════════════════════════════

class TestMe:
    def test_with_overridden_dependency_returns_user(self, overridden_client, regular_user):
        resp = overridden_client.get("/auth/me")

        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["email"] == regular_user.email
        assert data["user"]["id"] == regular_user.id

    def test_no_cookie_returns_401(self, auth_client):
        resp = auth_client.get("/auth/me")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Not authenticated"

    def test_garbage_cookie_returns_401(self, auth_client):
        settings = get_settings()
        auth_client.cookies.set(settings.COOKIE_NAME, "garbage-token-value")

        resp = auth_client.get("/auth/me")

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid or expired token"

    def test_valid_token_for_unknown_user_returns_401(self, auth_client, auth_mock_col):
        settings = get_settings()
        token = create_access_token("ghost@example.com")
        auth_client.cookies.set(settings.COOKIE_NAME, token)
        auth_mock_col.find_one.return_value = None

        resp = auth_client.get("/auth/me")

        assert resp.status_code == 401
        assert resp.json()["detail"] == "User not found"

    def test_valid_token_for_existing_user_returns_200(self, auth_client, auth_mock_col):
        settings = get_settings()
        doc = make_user_doc(email="student@test.edu")
        token = create_access_token("student@test.edu")
        auth_client.cookies.set(settings.COOKIE_NAME, token)
        auth_mock_col.find_one.return_value = doc

        resp = auth_client.get("/auth/me")

        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == "student@test.edu"


# ═══════════════════════════════════════════════════════════════════════════
# POST /auth/logout
# ═══════════════════════════════════════════════════════════════════════════

class TestLogout:
    def test_logout_returns_ok_and_clears_cookie(self, auth_client):
        resp = auth_client.post("/auth/logout")

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        settings = get_settings()
        set_cookie_header = resp.headers.get("set-cookie", "")
        assert settings.COOKIE_NAME in set_cookie_header
        # Cookie deletion sets an expiry in the past / empty value
        assert (
            f'{settings.COOKIE_NAME}=""' in set_cookie_header
            or f"{settings.COOKIE_NAME}=" in set_cookie_header
        )


# ═══════════════════════════════════════════════════════════════════════════
# POST /auth/consent
# ═══════════════════════════════════════════════════════════════════════════

class TestRecordConsentAgreement:
    def test_saves_consent_text_and_timestamp(self, overridden_client, auth_mock_col, regular_user):
        doc = make_user_doc(email=regular_user.email)
        auth_mock_col.find_one.return_value = doc

        resp = overridden_client.post("/auth/consent", json={
            "consent_text": "Research Consent Form ... I agree to participate",
        })

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        args, kwargs = auth_mock_col.update_one.call_args
        assert args[0] == {"_id": doc["_id"]}
        set_doc = args[1]["$set"]
        assert set_doc["consent_text"] == "Research Consent Form ... I agree to participate"
        assert "consent_agreed_at" in set_doc
        assert "updated_at" in set_doc

    def test_empty_consent_text_returns_422(self, overridden_client):
        resp = overridden_client.post("/auth/consent", json={"consent_text": ""})
        assert resp.status_code == 422

    def test_missing_field_returns_422(self, overridden_client):
        resp = overridden_client.post("/auth/consent", json={})
        assert resp.status_code == 422

    def test_user_not_found_returns_404(self, overridden_client, auth_mock_col):
        auth_mock_col.find_one.return_value = None

        resp = overridden_client.post("/auth/consent", json={"consent_text": "Some text"})

        assert resp.status_code == 404
        assert resp.json()["detail"] == "User not found"

    def test_requires_authentication(self, auth_client):
        resp = auth_client.post("/auth/consent", json={"consent_text": "Some text"})
        assert resp.status_code == 401

    def test_me_returns_saved_consent_text(self, auth_client, auth_mock_col):
        settings = get_settings()
        doc = make_user_doc(
            email="student@test.edu",
            consent_text="Research Consent Form ... I agree to participate",
            consent_agreed_at=datetime.now(timezone.utc),
        )
        token = create_access_token("student@test.edu")
        auth_client.cookies.set(settings.COOKIE_NAME, token)
        auth_mock_col.find_one.return_value = doc

        resp = auth_client.get("/auth/me")

        assert resp.status_code == 200
        assert resp.json()["user"]["consent_text"] == "Research Consent Form ... I agree to participate"
        assert resp.json()["user"]["consent_agreed_at"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# POST /auth/change-password
# ═══════════════════════════════════════════════════════════════════════════

class TestChangePassword:
    def test_successful_change(self, overridden_client, auth_mock_col, regular_user):
        doc = make_user_doc(email=regular_user.email, password="old-password")
        auth_mock_col.find_one.return_value = doc

        resp = overridden_client.post("/auth/change-password", json={
            "current_password": "old-password",
            "new_password": "new-password-123",
        })

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        # update_one called with new password_hash set
        args, _ = auth_mock_col.update_one.call_args
        assert args[0] == {"_id": doc["_id"]}
        assert "password_hash" in args[1]["$set"]
        assert args[1]["$set"]["password_hash"] != doc["password_hash"]

    def test_wrong_current_password_returns_400(self, overridden_client, auth_mock_col, regular_user):
        doc = make_user_doc(email=regular_user.email, password="old-password")
        auth_mock_col.find_one.return_value = doc

        resp = overridden_client.post("/auth/change-password", json={
            "current_password": "wrong-password",
            "new_password": "new-password-123",
        })

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Current password is incorrect"
        auth_mock_col.update_one.assert_not_called()

    def test_weak_new_password_returns_422(self, overridden_client, auth_mock_col, regular_user):
        doc = make_user_doc(email=regular_user.email, password="old-password")
        auth_mock_col.find_one.return_value = doc

        resp = overridden_client.post("/auth/change-password", json={
            "current_password": "old-password",
            "new_password": "abc",
        })

        assert resp.status_code == 422

    def test_user_not_found_returns_404(self, overridden_client, auth_mock_col):
        auth_mock_col.find_one.return_value = None

        resp = overridden_client.post("/auth/change-password", json={
            "current_password": "old-password",
            "new_password": "new-password-123",
        })

        assert resp.status_code == 404
        assert resp.json()["detail"] == "User not found"
