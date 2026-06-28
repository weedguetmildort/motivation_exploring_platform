# backend/tests/test_demographics_api.py
"""FastAPI TestClient integration tests for app/api/demographics.py.

Builds a local app/fixtures (does not modify tests/conftest.py) mounting only
the demographics router, with app.state.db backed by a MagicMock collection.
"""
from unittest.mock import MagicMock
from bson import ObjectId
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.demographics import router as demographics_router
from app.api.auth import get_current_user
from app.schemas.user import UserPublic


@pytest.fixture
def demo_user():
    return UserPublic(id=str(ObjectId()), email="student@test.edu", is_admin=False)


@pytest.fixture
def demo_app(mock_db, demo_user):
    app = FastAPI()
    app.include_router(demographics_router)
    app.state.db = mock_db
    app.dependency_overrides[get_current_user] = lambda: demo_user
    return app


@pytest.fixture
def demo_client(demo_app):
    return TestClient(demo_app)


VALID_PAYLOAD = {
    "gender": "female",
    "race_ethnicity": ["Asian", "White"],
    "age": "18-24",
    "academic_level": "Undergraduate",
    "year": "Junior",
    "major": "Computer Science",
    "class_name": "CS101",
}


class TestSaveMyDemographics:
    def test_success_sets_demographics_completed(self, demo_client, mock_col):
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        resp = demo_client.post("/demographics/me", json=VALID_PAYLOAD)

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        mock_col.update_one.assert_called_once()
        call_args = mock_col.update_one.call_args
        set_doc = call_args[0][1]["$set"]
        assert set_doc["demographics_completed"] is True
        assert set_doc["demographics"]["gender"] == "female"
        assert set_doc["demographics"]["race_ethnicity"] == ["Asian", "White"]
        assert set_doc["demographics"]["age"] == "18-24"
        assert set_doc["demographics"]["year"] == "Junior"
        assert "updated_at" in set_doc

    def test_filters_by_user_id(self, demo_client, mock_col, demo_user):
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        demo_client.post("/demographics/me", json=VALID_PAYLOAD)

        call_args = mock_col.update_one.call_args
        query = call_args[0][0]
        assert query == {"_id": ObjectId(demo_user.id)}

    def test_user_not_found_returns_404(self, demo_client, mock_col):
        mock_col.update_one.return_value = MagicMock(matched_count=0)

        resp = demo_client.post("/demographics/me", json=VALID_PAYLOAD)

        assert resp.status_code == 404
        assert resp.json()["detail"] == "User not found"

    def test_minimal_payload_with_only_required_fields(self, demo_client, mock_col):
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        resp = demo_client.post("/demographics/me", json={
            "gender": "male",
            "age": "25-34",
            "academic_level": "Masters",
            "year": "Senior",
        })

        assert resp.status_code == 200
        set_doc = mock_col.update_one.call_args[0][1]["$set"]
        assert set_doc["demographics"]["gender"] == "male"
        assert set_doc["demographics"]["race_ethnicity"] == []
        assert set_doc["demographics"]["other_gender"] is None
        assert set_doc["demographics"]["academic_level"] == "Masters"
        assert set_doc["demographics"]["other_academic_level"] is None
        assert set_doc["demographics"]["major"] is None
        assert set_doc["demographics"]["other_major"] is None
        assert set_doc["demographics"]["class_name"] is None

    def test_other_gender_and_other_major_fields(self, demo_client, mock_col):
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        payload = dict(VALID_PAYLOAD)
        payload["gender"] = "other"
        payload["other_gender"] = "Non-binary"
        payload["major"] = "Other"
        payload["other_major"] = "Cognitive Science"

        resp = demo_client.post("/demographics/me", json=payload)

        assert resp.status_code == 200
        set_doc = mock_col.update_one.call_args[0][1]["$set"]
        assert set_doc["demographics"]["other_gender"] == "Non-binary"
        assert set_doc["demographics"]["other_major"] == "Cognitive Science"

    def test_missing_gender_returns_422(self, demo_client):
        payload = dict(VALID_PAYLOAD)
        del payload["gender"]

        resp = demo_client.post("/demographics/me", json=payload)

        assert resp.status_code == 422

    def test_missing_age_returns_422(self, demo_client):
        payload = dict(VALID_PAYLOAD)
        del payload["age"]

        resp = demo_client.post("/demographics/me", json=payload)

        assert resp.status_code == 422

    def test_missing_year_returns_422(self, demo_client):
        payload = dict(VALID_PAYLOAD)
        del payload["year"]

        resp = demo_client.post("/demographics/me", json=payload)

        assert resp.status_code == 422

    def test_missing_academic_level_returns_422(self, demo_client):
        payload = dict(VALID_PAYLOAD)
        del payload["academic_level"]

        resp = demo_client.post("/demographics/me", json=payload)

        assert resp.status_code == 422

    def test_other_academic_level_field(self, demo_client, mock_col):
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        payload = dict(VALID_PAYLOAD)
        payload["academic_level"] = "Other"
        payload["other_academic_level"] = "Postdoctoral researcher"

        resp = demo_client.post("/demographics/me", json=payload)

        assert resp.status_code == 200
        set_doc = mock_col.update_one.call_args[0][1]["$set"]
        assert set_doc["demographics"]["academic_level"] == "Other"
        assert set_doc["demographics"]["other_academic_level"] == "Postdoctoral researcher"

    def test_invalid_race_ethnicity_type_returns_422(self, demo_client):
        payload = dict(VALID_PAYLOAD)
        payload["race_ethnicity"] = "not-a-list"

        resp = demo_client.post("/demographics/me", json=payload)

        assert resp.status_code == 422

    def test_empty_race_ethnicity_list_allowed(self, demo_client, mock_col):
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        payload = dict(VALID_PAYLOAD)
        payload["race_ethnicity"] = []

        resp = demo_client.post("/demographics/me", json=payload)

        assert resp.status_code == 200
        set_doc = mock_col.update_one.call_args[0][1]["$set"]
        assert set_doc["demographics"]["race_ethnicity"] == []

    def test_requires_authentication(self, mock_db, demo_user):
        """Without overriding get_current_user, requests should fail auth resolution."""
        app = FastAPI()
        app.include_router(demographics_router)
        app.state.db = mock_db
        client = TestClient(app)

        resp = client.post("/demographics/me", json=VALID_PAYLOAD)

        # No dependency override and no real auth backend configured -> not a 200
        assert resp.status_code != 200
