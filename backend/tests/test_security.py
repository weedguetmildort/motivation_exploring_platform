# backend/tests/test_security.py
"""Unit tests for app.core.security: password hashing and JWT helpers."""
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt, JWTError

from app.core.config import get_settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)


# ── hash_password / verify_password ─────────────────────────────────────────

class TestHashPassword:
    def test_round_trip(self):
        hashed = hash_password("correct horse battery staple")
        assert verify_password("correct horse battery staple", hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct horse battery staple")
        assert not verify_password("wrong password", hashed)

    def test_hash_is_not_plaintext(self):
        hashed = hash_password("mypassword")
        assert hashed != "mypassword"
        assert hashed.startswith("$argon2")

    def test_non_string_input_is_coerced(self):
        # int input should be coerced via str() before hashing
        hashed = hash_password(12345)
        assert verify_password("12345", hashed)
        assert verify_password(12345, hashed)

    def test_whitespace_is_stripped(self):
        hashed = hash_password("  mypassword  ")
        assert verify_password("mypassword", hashed)
        assert verify_password("  mypassword  ", hashed)

    def test_verify_non_string_input_is_coerced(self):
        hashed = hash_password("42")
        assert verify_password(42, hashed)


# ── create_access_token / decode_token ───────────────────────────────────────

class TestCreateAccessToken:
    def test_round_trip_returns_correct_subject(self):
        token = create_access_token("user@example.com")
        payload = decode_token(token)
        assert payload["sub"] == "user@example.com"

    def test_token_includes_iat_and_exp(self):
        token = create_access_token("user@example.com")
        payload = decode_token(token)
        assert "iat" in payload
        assert "exp" in payload
        assert payload["exp"] > payload["iat"]

    def test_exp_matches_configured_expiry(self):
        settings = get_settings()
        token = create_access_token("user@example.com")
        payload = decode_token(token)
        expected_delta = timedelta(minutes=settings.JWT_EXPIRES_MIN).total_seconds()
        actual_delta = payload["exp"] - payload["iat"]
        assert actual_delta == pytest.approx(expected_delta, abs=2)


class TestDecodeToken:
    def test_garbage_token_raises(self):
        with pytest.raises(JWTError):
            decode_token("not-a-valid-jwt")

    def test_empty_string_raises(self):
        with pytest.raises(JWTError):
            decode_token("")

    def test_token_signed_with_wrong_secret_raises(self):
        settings = get_settings()
        bad_token = jwt.encode(
            {"sub": "user@example.com", "iat": 0, "exp": 9999999999},
            "wrong-secret",
            algorithm=settings.JWT_ALG,
        )
        with pytest.raises(JWTError):
            decode_token(bad_token)

    def test_expired_token_raises(self):
        settings = get_settings()
        now = datetime.now(tz=timezone.utc)
        expired_payload = {
            "sub": "user@example.com",
            "iat": int((now - timedelta(minutes=10)).timestamp()),
            "exp": int((now - timedelta(minutes=1)).timestamp()),
        }
        expired_token = jwt.encode(
            expired_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG
        )
        with pytest.raises(JWTError):
            decode_token(expired_token)
