# backend/tests/test_surveys_api.py
"""FastAPI TestClient integration tests for app/api/surveys.py.

Builds a local app/fixtures (does not modify tests/conftest.py) mounting only
the surveys router, with app.state.db backed by a MagicMock collection.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock
from bson import ObjectId
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.surveys import router as surveys_router
from app.api.auth import get_current_user


# ── local app fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def survey_app(mock_db, regular_user):
    app = FastAPI()
    app.include_router(surveys_router)
    app.state.db = mock_db
    app.dependency_overrides[get_current_user] = lambda: regular_user
    return app


@pytest.fixture
def survey_client(survey_app):
    return TestClient(survey_app)


@pytest.fixture
def admin_survey_app(mock_db, admin_user):
    app = FastAPI()
    app.include_router(surveys_router)
    app.state.db = mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return app


@pytest.fixture
def admin_survey_client(admin_survey_app):
    return TestClient(admin_survey_app)


def make_item_doc(_id=None, stage="pre_quiz", prompt="Q1", item_type="likert", **overrides):
    doc = {
        "_id": _id if _id is not None else ObjectId(),
        "stage": stage,
        "prompt": prompt,
        "type": item_type,
        "required": True,
        "order": 0,
        "active": True,
        "category": None,
        "reverse_scored": False,
        "scale": {"min": 1, "max": 5, "anchors": ["Strongly disagree", "Strongly agree"]} if item_type == "likert" else None,
        "options": [{"id": "a", "label": "Yes"}, {"id": "b", "label": "No"}] if item_type == "single_select" else None,
    }
    doc.update(overrides)
    return doc


def make_response_doc(_id=None, user_id="userid1", user_email="student@test.edu", stage="pre_quiz", answers=None, status="in_progress"):
    now = datetime.now(timezone.utc)
    return {
        "_id": _id if _id is not None else ObjectId(),
        "user_id": user_id,
        "user_email": user_email,
        "stage": stage,
        "status": status,
        "answers": answers or [],
        "started_at": now,
        "completed_at": None,
        "updated_at": now,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Admin CRUD: /surveys/items
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdminCreateItem:
    def test_non_admin_gets_403(self, survey_client):
        resp = survey_client.post("/surveys/items", json={"stage": "pre_quiz", "prompt": "How are you?"})
        assert resp.status_code == 403

    def test_admin_creates_likert_item(self, admin_survey_client, mock_col):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        resp = admin_survey_client.post("/surveys/items", json={
            "stage": "pre_quiz",
            "prompt": "How motivated are you?",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(oid)
        assert data["prompt"] == "How motivated are you?"
        assert data["type"] == "likert"
        assert data["scale"] is not None

    def test_admin_creates_single_select_item(self, admin_survey_client, mock_col):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        resp = admin_survey_client.post("/surveys/items", json={
            "stage": "pre_quiz",
            "prompt": "Pick one",
            "type": "single_select",
            "options": [{"id": "a", "label": "Yes"}, {"id": "b", "label": "No"}],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "single_select"
        assert len(data["options"]) == 2

    def test_single_select_with_one_option_returns_422(self, admin_survey_client):
        resp = admin_survey_client.post("/surveys/items", json={
            "stage": "pre_quiz",
            "prompt": "Pick one",
            "type": "single_select",
            "options": [{"id": "a", "label": "Only one"}],
        })
        assert resp.status_code == 422

    def test_missing_prompt_returns_422(self, admin_survey_client):
        resp = admin_survey_client.post("/surveys/items", json={"stage": "pre_quiz", "prompt": ""})
        assert resp.status_code == 422

    def test_missing_required_fields_returns_422(self, admin_survey_client):
        resp = admin_survey_client.post("/surveys/items", json={"prompt": "Missing stage"})
        assert resp.status_code == 422


class TestAdminListItems:
    def test_non_admin_gets_403(self, survey_client):
        resp = survey_client.get("/surveys/items")
        assert resp.status_code == 403

    def test_admin_lists_items(self, admin_survey_client, mock_col):
        item = make_item_doc()
        mock_col.find.return_value.sort.return_value = [item]

        resp = admin_survey_client.get("/surveys/items")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == str(item["_id"])

    def test_admin_lists_items_filtered_by_stage(self, admin_survey_client, mock_col):
        mock_col.find.return_value.sort.return_value = []

        resp = admin_survey_client.get("/surveys/items?stage=post_base")

        assert resp.status_code == 200
        mock_col.find.assert_called_with({"stage": "post_base"})

    def test_empty_list_returns_empty_array(self, admin_survey_client, mock_col):
        mock_col.find.return_value.sort.return_value = []
        resp = admin_survey_client.get("/surveys/items")
        assert resp.status_code == 200
        assert resp.json() == []


class TestAdminUpdateItem:
    def test_non_admin_gets_403(self, survey_client):
        resp = survey_client.put(f"/surveys/items/{ObjectId()}", json={"prompt": "Updated"})
        assert resp.status_code == 403

    def test_admin_updates_item(self, admin_survey_client, mock_col):
        oid = ObjectId()
        existing = make_item_doc(_id=oid, prompt="Old")
        updated = make_item_doc(_id=oid, prompt="New")
        mock_col.find_one.side_effect = [existing, updated]

        resp = admin_survey_client.put(f"/surveys/items/{oid}", json={"prompt": "New"})

        assert resp.status_code == 200
        assert resp.json()["prompt"] == "New"

    def test_update_not_found_returns_404(self, admin_survey_client, mock_col):
        mock_col.find_one.return_value = None

        resp = admin_survey_client.put(f"/surveys/items/{ObjectId()}", json={"prompt": "New"})

        assert resp.status_code == 404

    def test_update_with_invalid_type_change_returns_400(self, admin_survey_client, mock_col):
        oid = ObjectId()
        existing = make_item_doc(_id=oid, item_type="likert")
        mock_col.find_one.return_value = existing

        # Switching to single_select without options should be rejected (400)
        resp = admin_survey_client.put(f"/surveys/items/{oid}", json={"type": "single_select"})

        assert resp.status_code == 400


class TestAdminDeleteItem:
    def test_non_admin_gets_403(self, survey_client):
        resp = survey_client.delete(f"/surveys/items/{ObjectId()}")
        assert resp.status_code == 403

    def test_admin_deletes_item(self, admin_survey_client, mock_col):
        mock_col.delete_one.return_value = MagicMock(deleted_count=1)

        resp = admin_survey_client.delete(f"/surveys/items/{ObjectId()}")

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_delete_not_found_returns_404(self, admin_survey_client, mock_col):
        mock_col.delete_one.return_value = MagicMock(deleted_count=0)

        resp = admin_survey_client.delete(f"/surveys/items/{ObjectId()}")

        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# User flow: /surveys/{stage}/state, /record_shown, /submit
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetState:
    def test_returns_state_for_new_user(self, survey_client, mock_col):
        mock_col.find.return_value.sort.return_value = []  # no items
        mock_col.find_one.return_value = None  # no existing response doc
        mock_col.insert_one.return_value = MagicMock(inserted_id=ObjectId())

        resp = survey_client.get("/surveys/pre_quiz/state")

        assert resp.status_code == 200
        data = resp.json()
        assert data["attempt"]["stage"] == "pre_quiz"
        assert data["attempt"]["status"] == "in_progress"
        assert data["attempt"]["answered_count"] == 0
        assert data["attempt"]["total_items"] == 0
        assert data["items"] == []
        assert data["answers"] == []

    def test_returns_state_with_items_and_answers(self, survey_client, mock_col):
        item_oid = ObjectId()
        item = make_item_doc(_id=item_oid)
        mock_col.find.return_value.sort.return_value = [item]

        now = datetime.now(timezone.utc)
        response_doc = make_response_doc(answers=[
            {"item_id": str(item_oid), "value": 4, "shown_at": now, "answered_at": now}
        ])
        mock_col.find_one.return_value = response_doc

        resp = survey_client.get("/surveys/pre_quiz/state")

        assert resp.status_code == 200
        data = resp.json()
        assert data["attempt"]["total_items"] == 1
        assert data["attempt"]["answered_count"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == str(item_oid)
        assert len(data["answers"]) == 1
        assert data["answers"][0]["value"] == 4

    def test_invalid_stage_returns_400(self, survey_client, mock_col):
        resp = survey_client.get("/surveys/not_a_real_stage/state")
        assert resp.status_code == 400


class TestRecordShown:
    def test_records_item_shown(self, survey_client, mock_col):
        resp = survey_client.post("/surveys/pre_quiz/record_shown", params={"item_id": "abc123"})

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_col.update_one.assert_called_once()

    def test_missing_item_id_returns_422(self, survey_client):
        resp = survey_client.post("/surveys/pre_quiz/record_shown")
        assert resp.status_code == 422


class TestSubmit:
    def test_invalid_stage_returns_400(self, survey_client, mock_col):
        doc = make_response_doc()
        mock_col.find_one.return_value = doc

        resp = survey_client.post("/surveys/bogus_stage/submit", json={"answers": []})

        assert resp.status_code == 400

    def test_already_completed_returns_400(self, survey_client, mock_col):
        doc = make_response_doc(status="completed")
        mock_col.find_one.return_value = doc

        resp = survey_client.post("/surveys/pre_quiz/submit", json={"answers": []})

        assert resp.status_code == 400
        assert "already completed" in resp.json()["detail"].lower()

    def test_invalid_item_id_returns_400(self, survey_client, mock_col):
        doc = make_response_doc()
        mock_col.find_one.return_value = doc
        mock_col.find.return_value = []  # no valid item ids

        resp = survey_client.post("/surveys/pre_quiz/submit", json={
            "answers": [{"item_id": "not-a-real-item", "value": 4}]
        })

        assert resp.status_code == 400
        assert "Invalid survey item_id" in resp.json()["detail"]

    def test_missing_answers_field_returns_422(self, survey_client):
        resp = survey_client.post("/surveys/pre_quiz/submit", json={})
        assert resp.status_code == 422

    def test_partial_submit_keeps_in_progress(self, survey_client, mock_col):
        item1 = ObjectId()
        item2 = ObjectId()
        doc = make_response_doc(answers=[])

        updated_doc = dict(doc)
        updated_doc["answers"] = [
            {"item_id": str(item1), "value": 4, "shown_at": None, "answered_at": datetime.now(timezone.utc)},
        ]

        # find_one sequence: load_or_create, post-update read, build_survey_state's load
        mock_col.find_one.side_effect = [doc, updated_doc, updated_doc]
        mock_col.update_one.return_value = MagicMock(matched_count=0)

        final_find_result = MagicMock()
        final_find_result.sort.return_value = []
        mock_col.find.side_effect = [
            [{"_id": item1}, {"_id": item2}],  # valid_ids
            [{"_id": item1}, {"_id": item2}],  # required_ids -> both required
            final_find_result,  # build_survey_state's list_survey_items
        ]

        resp = survey_client.post("/surveys/pre_quiz/submit", json={
            "answers": [{"item_id": str(item1), "value": 4}]
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["attempt"]["status"] == "in_progress"

    def test_full_completion_returns_completed_state(self, survey_client, mock_col, regular_user):
        item1 = ObjectId()
        user_oid = ObjectId()
        # Override regular_user's id to a valid ObjectId hex string for this test
        # (the completion path calls ObjectId(user_id) on the users collection).
        from app.api.auth import get_current_user
        from app.schemas.user import UserPublic

        completed_now = datetime.now(timezone.utc)
        doc = make_response_doc(user_id=str(user_oid), answers=[])
        updated_doc = dict(doc)
        updated_doc["answers"] = [
            {"item_id": str(item1), "value": 5, "shown_at": None, "answered_at": completed_now},
        ]
        updated_doc["status"] = "completed"

        mock_col.find_one.side_effect = [doc, updated_doc, updated_doc]
        mock_col.update_one.side_effect = [
            MagicMock(matched_count=1),  # answer update
            MagicMock(),  # completion status update
            MagicMock(matched_count=1),  # user update
        ]

        final_find_result = MagicMock()
        final_find_result.sort.return_value = []
        mock_col.find.side_effect = [
            [{"_id": item1}],  # valid_ids
            [{"_id": item1}],  # required_ids
            final_find_result,  # build_survey_state's list_survey_items
        ]

        # Override the current user to have a valid ObjectId-format id
        survey_client.app.dependency_overrides[get_current_user] = lambda: UserPublic(
            id=str(user_oid), email="student@test.edu", is_admin=False,
        )

        resp = survey_client.post("/surveys/pre_quiz/submit", json={
            "answers": [{"item_id": str(item1), "value": 5}]
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["attempt"]["status"] == "completed"

        # The user doc should have been updated with completion flags
        user_update_call = mock_col.update_one.call_args_list[-1]
        set_doc = user_update_call[0][1]["$set"]
        assert set_doc["survey_pre_base_completed"] is True
        assert set_doc["pre_quiz_survey"] == {str(item1): 5}
