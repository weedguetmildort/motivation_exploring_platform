# backend/tests/test_questions.py
"""Unit tests for app/services/questions.py and API tests for app/api/questions.py."""
from datetime import datetime
from unittest.mock import MagicMock
from bson import ObjectId
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.services.questions import (
    get_questions_collection,
    create_question,
    list_questions,
    update_question,
    delete_question,
)
from app.schemas.question import QuestionCreate, QuestionChoice, QuestionUpdate
from app.api.questions import router as questions_router
from app.api.auth import get_current_user


# ═══════════════════════════════════════════════════════════════════════════
# Service-layer unit tests
# ═══════════════════════════════════════════════════════════════════════════

class TestGetQuestionsCollection:
    def test_returns_questions_collection(self, mock_db, mock_col):
        assert get_questions_collection(mock_db) is mock_col
        mock_db.__getitem__.assert_any_call("questions")


class TestCreateQuestion:
    def test_creates_question_and_returns_admin_public(self):
        col = MagicMock()
        oid = ObjectId()
        col.insert_one.return_value = MagicMock(inserted_id=oid)

        data = QuestionCreate(
            stem="What is 2+2?",
            subtitle="Basic math",
            choices=[
                QuestionChoice(id="a", label="3"),
                QuestionChoice(id="b", label="4"),
            ],
            correct_choice_id="b",
        )

        result = create_question(col, data)

        assert result.id == str(oid)
        assert result.stem == "What is 2+2?"
        assert result.subtitle == "Basic math"
        assert result.correct_choice_id == "b"
        assert result.choices == [
            QuestionChoice(id="a", label="3"),
            QuestionChoice(id="b", label="4"),
        ]

        # The inserted document should include metadata fields
        inserted_doc = col.insert_one.call_args[0][0]
        assert inserted_doc["active"] is True
        assert "created_at" in inserted_doc
        assert inserted_doc["correct_choice_id"] == "b"

    def test_creates_question_without_subtitle(self):
        col = MagicMock()
        col.insert_one.return_value = MagicMock(inserted_id=ObjectId())

        data = QuestionCreate(
            stem="Stemless?",
            choices=[QuestionChoice(id="a", label="Yes"), QuestionChoice(id="b", label="No")],
            correct_choice_id="a",
        )

        result = create_question(col, data)

        assert result.subtitle is None


class TestListQuestions:
    def test_returns_list_of_admin_public_questions(self, mock_col):
        oid1 = ObjectId()
        oid2 = ObjectId()
        docs = [
            {
                "_id": oid1,
                "stem": "Q1",
                "subtitle": "Sub1",
                "choices": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                "correct_choice_id": "a",
                "created_at": datetime.utcnow(),
            },
            {
                "_id": oid2,
                "stem": "Q2",
                "choices": [{"id": "a", "label": "A2"}],
                "correct_choice_id": "a",
                "created_at": datetime.utcnow(),
            },
        ]
        mock_col.find.return_value.sort.return_value.limit.return_value = docs

        result = list_questions(mock_col)

        assert len(result) == 2
        assert result[0].id == str(oid1)
        assert result[0].stem == "Q1"
        assert result[0].subtitle == "Sub1"
        assert result[1].id == str(oid2)
        # subtitle defaults to None when missing
        assert result[1].subtitle is None

    def test_empty_collection_returns_empty_list(self, mock_col):
        mock_col.find.return_value.sort.return_value.limit.return_value = []

        result = list_questions(mock_col)

        assert result == []

    def test_default_limit_is_passed(self, mock_col):
        mock_col.find.return_value.sort.return_value.limit.return_value = []

        list_questions(mock_col)

        mock_col.find.return_value.sort.return_value.limit.assert_called_once_with(100)

    def test_custom_limit_is_passed(self, mock_col):
        mock_col.find.return_value.sort.return_value.limit.return_value = []

        list_questions(mock_col, limit=5)

        mock_col.find.return_value.sort.return_value.limit.assert_called_once_with(5)

    def test_missing_correct_choice_id_defaults_to_empty_string(self, mock_col):
        oid = ObjectId()
        docs = [
            {
                "_id": oid,
                "stem": "Q1",
                "choices": [{"id": "a", "label": "A"}],
                # no correct_choice_id key
            },
        ]
        mock_col.find.return_value.sort.return_value.limit.return_value = docs

        result = list_questions(mock_col)

        assert result[0].correct_choice_id == ""


class TestUpdateQuestion:
    def test_updates_existing_question(self, mock_col):
        oid = ObjectId()
        updated_doc = {
            "_id": oid,
            "stem": "Updated stem",
            "subtitle": "Updated subtitle",
            "choices": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "correct_choice_id": "b",
        }
        mock_col.find_one_and_update.return_value = updated_doc

        data = QuestionUpdate(
            stem="Updated stem",
            subtitle="Updated subtitle",
            choices=[QuestionChoice(id="a", label="A"), QuestionChoice(id="b", label="B")],
            correct_choice_id="b",
        )

        result = update_question(mock_col, str(oid), data)

        assert result.id == str(oid)
        assert result.stem == "Updated stem"
        assert result.correct_choice_id == "b"

        # check the update document passed to mongo
        call_args = mock_col.find_one_and_update.call_args
        assert call_args[0][0] == {"_id": oid}
        set_doc = call_args[0][1]["$set"]
        assert set_doc["stem"] == "Updated stem"
        assert set_doc["correct_choice_id"] == "b"

    def test_invalid_object_id_raises_400(self, mock_col):
        data = QuestionUpdate(
            stem="X",
            choices=[QuestionChoice(id="a", label="A")],
            correct_choice_id="a",
        )

        with pytest.raises(HTTPException) as exc_info:
            update_question(mock_col, "not-an-object-id", data)

        assert exc_info.value.status_code == 400
        assert "Invalid question id" in exc_info.value.detail
        mock_col.find_one_and_update.assert_not_called()

    def test_not_found_raises_404(self, mock_col):
        mock_col.find_one_and_update.return_value = None

        data = QuestionUpdate(
            stem="X",
            choices=[QuestionChoice(id="a", label="A")],
            correct_choice_id="a",
        )

        with pytest.raises(HTTPException) as exc_info:
            update_question(mock_col, str(ObjectId()), data)

        assert exc_info.value.status_code == 404
        assert "Question not found" in exc_info.value.detail

    def test_missing_correct_choice_id_in_result_defaults_empty(self, mock_col):
        oid = ObjectId()
        mock_col.find_one_and_update.return_value = {
            "_id": oid,
            "stem": "X",
            "choices": [{"id": "a", "label": "A"}],
            # no correct_choice_id
        }

        data = QuestionUpdate(
            stem="X",
            choices=[QuestionChoice(id="a", label="A")],
            correct_choice_id="a",
        )

        result = update_question(mock_col, str(oid), data)
        assert result.correct_choice_id == ""


class TestDeleteQuestion:
    def test_deletes_existing_question(self, mock_col):
        mock_col.delete_one.return_value = MagicMock(deleted_count=1)
        oid = ObjectId()

        delete_question(mock_col, str(oid))

        mock_col.delete_one.assert_called_once_with({"_id": oid})

    def test_invalid_object_id_raises_400(self, mock_col):
        with pytest.raises(HTTPException) as exc_info:
            delete_question(mock_col, "not-an-object-id")

        assert exc_info.value.status_code == 400
        assert "Invalid question id" in exc_info.value.detail
        mock_col.delete_one.assert_not_called()

    def test_not_found_raises_404(self, mock_col):
        mock_col.delete_one.return_value = MagicMock(deleted_count=0)

        with pytest.raises(HTTPException) as exc_info:
            delete_question(mock_col, str(ObjectId()))

        assert exc_info.value.status_code == 404
        assert "Question not found" in exc_info.value.detail


# ═══════════════════════════════════════════════════════════════════════════
# API integration tests
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def questions_app(admin_user, mock_db):
    app = FastAPI()
    app.include_router(questions_router)
    app.state.db = mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return app


@pytest.fixture
def questions_client(questions_app):
    return TestClient(questions_app)


@pytest.fixture
def questions_app_unauthed(regular_user, mock_db):
    app = FastAPI()
    app.include_router(questions_router)
    app.state.db = mock_db
    app.dependency_overrides[get_current_user] = lambda: regular_user
    return app


@pytest.fixture
def questions_client_unauthed(questions_app_unauthed):
    return TestClient(questions_app_unauthed)


VALID_QUESTION_PAYLOAD = {
    "stem": "What is 2+2?",
    "subtitle": "Basic math",
    "choices": [
        {"id": "a", "label": "3"},
        {"id": "b", "label": "4"},
    ],
    "correct_choice_id": "b",
}


class TestCreateQuestionEndpoint:
    def test_admin_can_create_question(self, questions_client, mock_col):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        resp = questions_client.post("/questions", json=VALID_QUESTION_PAYLOAD)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(oid)
        assert data["stem"] == "What is 2+2?"
        assert data["correct_choice_id"] == "b"

    def test_non_admin_forbidden(self, questions_client_unauthed):
        resp = questions_client_unauthed.post("/questions", json=VALID_QUESTION_PAYLOAD)
        assert resp.status_code == 403

    def test_missing_required_field_returns_422(self, questions_client):
        bad_payload = {k: v for k, v in VALID_QUESTION_PAYLOAD.items() if k != "stem"}
        resp = questions_client.post("/questions", json=bad_payload)
        assert resp.status_code == 422

    def test_missing_correct_choice_id_returns_422(self, questions_client):
        bad_payload = {k: v for k, v in VALID_QUESTION_PAYLOAD.items() if k != "correct_choice_id"}
        resp = questions_client.post("/questions", json=bad_payload)
        assert resp.status_code == 422


class TestListQuestionsEndpoint:
    def test_admin_can_list_questions(self, questions_client, mock_col):
        oid = ObjectId()
        docs = [{
            "_id": oid,
            "stem": "Q1",
            "subtitle": None,
            "choices": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "correct_choice_id": "a",
            "created_at": datetime.utcnow(),
        }]
        mock_col.find.return_value.sort.return_value.limit.return_value = docs

        resp = questions_client.get("/questions")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == str(oid)
        assert data[0]["stem"] == "Q1"

    def test_empty_list(self, questions_client, mock_col):
        mock_col.find.return_value.sort.return_value.limit.return_value = []

        resp = questions_client.get("/questions")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_non_admin_forbidden(self, questions_client_unauthed):
        resp = questions_client_unauthed.get("/questions")
        assert resp.status_code == 403


class TestUpdateQuestionEndpoint:
    def test_admin_can_update_question(self, questions_client, mock_col):
        oid = ObjectId()
        mock_col.find_one_and_update.return_value = {
            "_id": oid,
            "stem": "Updated",
            "subtitle": "Updated sub",
            "choices": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "correct_choice_id": "a",
        }

        payload = {**VALID_QUESTION_PAYLOAD, "stem": "Updated", "correct_choice_id": "a"}
        resp = questions_client.put(f"/questions/{oid}", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["stem"] == "Updated"
        assert data["correct_choice_id"] == "a"

    def test_non_admin_forbidden(self, questions_client_unauthed):
        resp = questions_client_unauthed.put(f"/questions/{ObjectId()}", json=VALID_QUESTION_PAYLOAD)
        assert resp.status_code == 403

    def test_invalid_id_returns_400(self, questions_client, mock_col):
        resp = questions_client.put("/questions/not-an-object-id", json=VALID_QUESTION_PAYLOAD)
        assert resp.status_code == 400

    def test_not_found_returns_404(self, questions_client, mock_col):
        mock_col.find_one_and_update.return_value = None

        resp = questions_client.put(f"/questions/{ObjectId()}", json=VALID_QUESTION_PAYLOAD)

        assert resp.status_code == 404

    def test_missing_field_returns_422(self, questions_client):
        bad_payload = {k: v for k, v in VALID_QUESTION_PAYLOAD.items() if k != "choices"}
        resp = questions_client.put(f"/questions/{ObjectId()}", json=bad_payload)
        assert resp.status_code == 422


class TestDeleteQuestionEndpoint:
    def test_admin_can_delete_question(self, questions_client, mock_col):
        mock_col.delete_one.return_value = MagicMock(deleted_count=1)
        oid = ObjectId()

        resp = questions_client.delete(f"/questions/{oid}")

        assert resp.status_code == 204
        mock_col.delete_one.assert_called_once_with({"_id": oid})

    def test_non_admin_forbidden(self, questions_client_unauthed, mock_col):
        resp = questions_client_unauthed.delete(f"/questions/{ObjectId()}")
        assert resp.status_code == 403
        mock_col.delete_one.assert_not_called()

    def test_invalid_id_returns_400(self, questions_client, mock_col):
        resp = questions_client.delete("/questions/not-an-object-id")
        assert resp.status_code == 400

    def test_not_found_returns_404(self, questions_client, mock_col):
        mock_col.delete_one.return_value = MagicMock(deleted_count=0)

        resp = questions_client.delete(f"/questions/{ObjectId()}")

        assert resp.status_code == 404
