# backend/tests/test_questions.py
"""Unit tests for app/services/questions.py and API tests for app/api/questions.py."""
from datetime import datetime
from unittest.mock import MagicMock, patch
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
    assign_set,
    override_difficulty,
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


class TestCreateQuestionSetAndDifficultyDefaults:
    def test_new_question_defaults_unassigned_and_unjudged(self):
        col = MagicMock()
        col.insert_one.return_value = MagicMock(inserted_id=ObjectId())
        data = QuestionCreate(
            stem="Stats",
            choices=[QuestionChoice(id="a", label="1"), QuestionChoice(id="b", label="2")],
            correct_choice_id="a",
        )

        result = create_question(col, data)

        assert result.set is None
        assert result.difficulty is None
        assert result.difficulty_source is None
        assert result.difficulty_checked is False
        inserted = col.insert_one.call_args[0][0]
        assert inserted["difficulty_checked"] is False
        assert inserted["set"] is None

    def test_create_persists_assigned_set(self):
        col = MagicMock()
        col.insert_one.return_value = MagicMock(inserted_id=ObjectId())
        data = QuestionCreate(
            stem="Stats",
            choices=[QuestionChoice(id="a", label="1"), QuestionChoice(id="b", label="2")],
            correct_choice_id="a",
            set="b",
        )
        result = create_question(col, data)
        assert result.set == "b"


class TestAssignSet:
    def test_assigns_set(self, mock_col):
        oid = ObjectId()
        mock_col.find_one_and_update.return_value = {
            "_id": oid, "stem": "Q", "choices": [{"id": "a", "label": "A"}],
            "correct_choice_id": "a", "set": "c",
        }
        result = assign_set(mock_col, str(oid), "c")
        assert result.set == "c"
        assert mock_col.find_one_and_update.call_args[0][1] == {"$set": {"set": "c"}}

    def test_clear_set(self, mock_col):
        oid = ObjectId()
        mock_col.find_one_and_update.return_value = {
            "_id": oid, "stem": "Q", "choices": [{"id": "a", "label": "A"}],
            "correct_choice_id": "a", "set": None,
        }
        result = assign_set(mock_col, str(oid), None)
        assert result.set is None

    def test_invalid_id_raises_400(self, mock_col):
        with pytest.raises(HTTPException) as exc:
            assign_set(mock_col, "nope", "a")
        assert exc.value.status_code == 400

    def test_not_found_raises_404(self, mock_col):
        mock_col.find_one_and_update.return_value = None
        with pytest.raises(HTTPException) as exc:
            assign_set(mock_col, str(ObjectId()), "a")
        assert exc.value.status_code == 404


class TestOverrideDifficulty:
    def test_manual_override_marks_source_and_checked(self, mock_col):
        oid = ObjectId()
        mock_col.find_one_and_update.return_value = {
            "_id": oid, "stem": "Q", "choices": [{"id": "a", "label": "A"}],
            "correct_choice_id": "a",
            "difficulty": "hard", "difficulty_source": "manual", "difficulty_checked": True,
        }
        result = override_difficulty(mock_col, str(oid), "hard")
        assert result.difficulty == "hard"
        assert result.difficulty_source == "manual"
        assert result.difficulty_checked is True
        set_doc = mock_col.find_one_and_update.call_args[0][1]["$set"]
        assert set_doc == {"difficulty": "hard", "difficulty_source": "manual", "difficulty_checked": True}

    def test_clearing_difficulty_returns_to_unjudged(self, mock_col):
        oid = ObjectId()
        mock_col.find_one_and_update.return_value = {
            "_id": oid, "stem": "Q", "choices": [{"id": "a", "label": "A"}],
            "correct_choice_id": "a",
            "difficulty": None, "difficulty_source": None, "difficulty_checked": False,
        }
        override_difficulty(mock_col, str(oid), None)
        set_doc = mock_col.find_one_and_update.call_args[0][1]["$set"]
        assert set_doc == {"difficulty": None, "difficulty_source": None, "difficulty_checked": False}

    def test_invalid_id_raises_400(self, mock_col):
        with pytest.raises(HTTPException) as exc:
            override_difficulty(mock_col, "nope", "easy")
        assert exc.value.status_code == 400

    def test_not_found_raises_404(self, mock_col):
        mock_col.find_one_and_update.return_value = None
        with pytest.raises(HTTPException) as exc:
            override_difficulty(mock_col, str(ObjectId()), "easy")
        assert exc.value.status_code == 404


class TestUpdateResetsDifficultyOnEdit:
    def _payload(self):
        return QuestionUpdate(
            stem="Edited",
            choices=[QuestionChoice(id="a", label="A")],
            correct_choice_id="a",
        )

    def test_ai_difficulty_is_reset_on_content_edit(self, mock_col):
        oid = ObjectId()
        mock_col.find_one.return_value = {"_id": oid, "difficulty_source": "ai"}
        mock_col.find_one_and_update.return_value = {
            "_id": oid, "stem": "Edited", "choices": [{"id": "a", "label": "A"}],
            "correct_choice_id": "a",
        }
        update_question(mock_col, str(oid), self._payload())
        set_doc = mock_col.find_one_and_update.call_args[0][1]["$set"]
        assert set_doc["difficulty"] is None
        assert set_doc["difficulty_source"] is None
        assert set_doc["difficulty_checked"] is False

    def test_manual_difficulty_is_preserved_on_edit(self, mock_col):
        oid = ObjectId()
        mock_col.find_one.return_value = {"_id": oid, "difficulty_source": "manual"}
        mock_col.find_one_and_update.return_value = {
            "_id": oid, "stem": "Edited", "choices": [{"id": "a", "label": "A"}],
            "correct_choice_id": "a",
        }
        update_question(mock_col, str(oid), self._payload())
        set_doc = mock_col.find_one_and_update.call_args[0][1]["$set"]
        assert "difficulty" not in set_doc
        assert "difficulty_source" not in set_doc
        assert "difficulty_checked" not in set_doc

    def test_edit_does_not_write_set(self, mock_col):
        oid = ObjectId()
        mock_col.find_one.return_value = {"_id": oid, "difficulty_source": "manual"}
        mock_col.find_one_and_update.return_value = {
            "_id": oid, "stem": "Edited", "choices": [{"id": "a", "label": "A"}],
            "correct_choice_id": "a",
        }
        update_question(mock_col, str(oid), self._payload())
        set_doc = mock_col.find_one_and_update.call_args[0][1]["$set"]
        assert "set" not in set_doc

    def test_missing_question_raises_404(self, mock_col):
        mock_col.find_one.return_value = None
        with pytest.raises(HTTPException) as exc:
            update_question(mock_col, str(ObjectId()), self._payload())
        assert exc.value.status_code == 404
        mock_col.find_one_and_update.assert_not_called()


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


class TestAssignSetEndpoint:
    def test_admin_can_assign_set(self, questions_client, mock_col):
        oid = ObjectId()
        mock_col.find_one_and_update.return_value = {
            "_id": oid, "stem": "Q", "choices": [{"id": "a", "label": "A"}],
            "correct_choice_id": "a", "set": "b",
        }
        resp = questions_client.patch(f"/questions/{oid}/set", json={"set": "b"})
        assert resp.status_code == 200
        assert resp.json()["set"] == "b"

    def test_rejects_invalid_set_value(self, questions_client):
        resp = questions_client.patch(f"/questions/{ObjectId()}/set", json={"set": "z"})
        assert resp.status_code == 422

    def test_non_admin_forbidden(self, questions_client_unauthed):
        resp = questions_client_unauthed.patch(f"/questions/{ObjectId()}/set", json={"set": "a"})
        assert resp.status_code == 403


class TestOverrideDifficultyEndpoint:
    def test_admin_can_override_difficulty(self, questions_client, mock_col):
        oid = ObjectId()
        mock_col.find_one_and_update.return_value = {
            "_id": oid, "stem": "Q", "choices": [{"id": "a", "label": "A"}],
            "correct_choice_id": "a",
            "difficulty": "medium", "difficulty_source": "manual", "difficulty_checked": True,
        }
        resp = questions_client.patch(f"/questions/{oid}/difficulty", json={"difficulty": "medium"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["difficulty"] == "medium"
        assert body["difficulty_source"] == "manual"

    def test_rejects_invalid_difficulty_value(self, questions_client):
        resp = questions_client.patch(f"/questions/{ObjectId()}/difficulty", json={"difficulty": "trivial"})
        assert resp.status_code == 422

    def test_non_admin_forbidden(self, questions_client_unauthed):
        resp = questions_client_unauthed.patch(f"/questions/{ObjectId()}/difficulty", json={"difficulty": "easy"})
        assert resp.status_code == 403


class TestJudgeDifficultyEndpoint:
    def test_admin_triggers_judging_with_shared_gateway_client(self, questions_client, mock_db):
        fake_client = MagicMock()
        with patch("app.api.questions.get_sync_llm_client", return_value=fake_client) as mock_factory, \
             patch("app.api.questions.run_difficulty_judging", return_value={"judged": 3, "skipped": 1}) as mock_run:
            resp = questions_client.post("/questions/judge-difficulty")
        assert resp.status_code == 200
        assert resp.json() == {"judged": 3, "skipped": 1}
        # The endpoint builds its client from the central UF gateway factory and
        # passes it straight through to the judging pass.
        mock_factory.assert_called_once()
        mock_run.assert_called_once_with(mock_db, fake_client)

    def test_non_admin_forbidden(self, questions_client_unauthed):
        with patch("app.api.questions.run_difficulty_judging") as mock_run:
            resp = questions_client_unauthed.post("/questions/judge-difficulty")
        assert resp.status_code == 403
        mock_run.assert_not_called()
