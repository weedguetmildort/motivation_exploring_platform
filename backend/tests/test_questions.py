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
        mock_col.find.return_value.sort.return_value = docs

        result = list_questions(mock_col)

        assert len(result) == 2
        assert result[0].id == str(oid1)
        assert result[0].stem == "Q1"
        assert result[0].subtitle == "Sub1"
        assert result[1].id == str(oid2)
        # subtitle defaults to None when missing
        assert result[1].subtitle is None

    def test_empty_collection_returns_empty_list(self, mock_col):
        mock_col.find.return_value.sort.return_value = []

        result = list_questions(mock_col)

        assert result == []

    def test_lists_the_whole_bank_by_default(self, mock_col):
        # The panel's per-set counts are computed from this list, so it must not be a page.
        cursor = MagicMock()
        cursor.__iter__.return_value = iter([])
        mock_col.find.return_value.sort.return_value = cursor

        assert list_questions(mock_col) == []

        cursor.limit.assert_not_called()

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
        mock_col.find.return_value.sort.return_value = docs

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
        mock_col.find.return_value.sort.return_value = docs

        resp = questions_client.get("/questions")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == str(oid)
        assert data[0]["stem"] == "Q1"

    def test_empty_list(self, questions_client, mock_col):
        mock_col.find.return_value.sort.return_value = []

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


# ═══════════════════════════════════════════════════════════════════════════
# Correct-answer rule shared by the forms and the CSV import
# ═══════════════════════════════════════════════════════════════════════════

class TestCorrectChoiceMustBeOffered:
    def test_correct_choice_outside_the_choices_is_rejected(self):
        with pytest.raises(ValueError, match="correct_choice_id"):
            QuestionCreate(stem="T", choices=[QuestionChoice(id="a", label="1")], correct_choice_id="z")

    def test_edits_follow_the_same_rule(self):
        with pytest.raises(ValueError, match="correct_choice_id"):
            QuestionUpdate(stem="T", choices=[QuestionChoice(id="a", label="1")], correct_choice_id="")

    def test_create_endpoint_rejects_an_unknown_correct_choice(self, questions_client, mock_col):
        resp = questions_client.post("/questions", json={**VALID_QUESTION_PAYLOAD, "correct_choice_id": "d"})
        assert resp.status_code == 422
        mock_col.insert_one.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# CSV import
# ═══════════════════════════════════════════════════════════════════════════

from app.services.questions import parse_question_csv, import_questions, MAX_IMPORT_ROWS

HEADER = "topic,question,a,b,c,d,correct,set\n"
ROW = "Basic Probability,A jar contains 4 red and 6 blue,2/5,3/5,1/6,2/3,b,c\n"


def csv_text(*rows, header=HEADER):
    return header + "".join(rows)


@pytest.fixture
def bank():
    import mongomock
    return mongomock.MongoClient().db["questions"]


class TestParseQuestionCsv:
    def test_reads_a_valid_row_into_a_question(self):
        questions, errors, rows = parse_question_csv(csv_text(ROW))
        assert errors == [] and rows == 1
        row, question = questions[0]
        assert row == 2
        assert question.stem == "Basic Probability" and question.subtitle == "A jar contains 4 red and 6 blue"
        assert [(c.id, c.label) for c in question.choices] == [("a", "2/5"), ("b", "3/5"), ("c", "1/6"), ("d", "2/3")]
        assert question.correct_choice_id == "b" and question.set == "c"

    def test_headers_and_letters_are_case_insensitive_and_trimmed(self):
        text = csv_text(" Combinatorics , How many ways? , 12 , 7 , 24 , 4 , A , D \n",
                        header=" Topic , QUESTION ,A,B,C,D, Correct , Set \n")
        (_, question), = parse_question_csv(text)[0]
        assert question.stem == "Combinatorics" and question.correct_choice_id == "a" and question.set == "d"
        assert question.choices[0].label == "12"

    def test_set_column_may_be_left_out_or_blank(self):
        no_column = csv_text("T,Q,1,2,3,4,a\n", header="topic,question,a,b,c,d,correct\n")
        blank = csv_text("T,Q,1,2,3,4,a,\n")
        assert parse_question_csv(no_column)[0][0][1].set is None
        assert parse_question_csv(blank)[0][0][1].set is None

    def test_question_text_may_be_blank_like_the_form(self):
        (_, question), = parse_question_csv(csv_text("T,,1,2,3,4,a,\n"))[0]
        assert question.subtitle is None

    def test_columns_may_come_in_any_order(self):
        text = csv_text("c,4,3,2,1,T,Q,b\n", header="set,d,c,b,a,topic,question,correct\n")
        (_, question), = parse_question_csv(text)[0]
        assert [c.label for c in question.choices] == ["1", "2", "3", "4"] and question.set == "c"

    def test_quoted_cells_keep_commas_and_line_breaks(self):
        text = csv_text('"Statistical Inference","A 95% confidence interval, computed\nfrom a sample","(0.08, 7.92)","b","c","d",a,\n')
        (row, question), = parse_question_csv(text)[0]
        assert question.subtitle == "A 95% confidence interval, computed\nfrom a sample"
        assert question.choices[0].label == "(0.08, 7.92)"
        assert row == 2

    def test_excel_byte_order_mark_is_ignored(self):
        assert parse_question_csv("﻿" + csv_text(ROW))[1] == []

    def test_blank_rows_are_skipped_but_keep_row_numbers_aligned(self):
        questions, errors, rows = parse_question_csv(csv_text(ROW, ",,,,,,,\n", "\n", "T,Q,1,2,3,4,z,\n"))
        assert rows == 2
        assert errors[0].row == 5  # the spreadsheet row, counting the blank rows above it

    @pytest.mark.parametrize("header,message", [
        ("topic,question,a,b,c,d,correct,set,difficulty\n", "Unknown column(s): difficulty"),
        ("topic,question,a,b,c,correct\n", "Missing column(s): d"),
        ("topic,question,a,b,c,d,correct,set,set\n", "Repeated column(s): set"),
        ("stem,subtitle,choices[0].id,a,b,c,d,correct_choice_id\n",
         "Unknown column(s): stem, subtitle, choices[0].id, correct_choice_id"),
    ])
    def test_a_bad_header_is_reported_once_on_row_1(self, header, message):
        questions, errors, rows = parse_question_csv(csv_text(ROW, header=header))
        assert questions == [] and rows == 0 and len(errors) == 1
        assert errors[0].row == 1 and message in errors[0].message
        assert "Expected: topic, question, a, b, c, d, correct, set" in errors[0].message

    @pytest.mark.parametrize("text", ["", "\n", ",,,\n"])
    def test_an_empty_file_is_reported(self, text):
        errors = parse_question_csv(text)[1]
        assert [(e.row, e.message) for e in errors] == [(1, "The file is empty")]

    @pytest.mark.parametrize("row,message", [
        (",Q,1,2,3,4,a,\n", "topic is empty"),
        ("T,Q,1,,3,4,a,\n", "choice b is empty"),
        ("T,Q,1,2,3,4,e,\n", "correct must be a, b, c or d (found 'e')"),
        ("T,Q,1,2,3,4,,\n", "correct must be a, b, c or d (found '')"),
        ("T,Q,1,2,3,4,a,e\n", "set must be blank or one of a, b, c, d (found 'e')"),
        ("T,Q,1,2,3,4,a,c,extra\n", "the row has more cells than the header"),
    ])
    def test_row_problems_are_reported_with_their_row(self, row, message):
        questions, errors, _ = parse_question_csv(csv_text(ROW, row))
        assert len(questions) == 1
        assert errors[0].row == 3 and message in errors[0].message

    def test_every_problem_in_a_row_is_reported_together(self):
        errors = parse_question_csv(csv_text(",Q,,2,3,4,x,z\n"))[1]
        assert errors[0].message == ("topic is empty; choice a is empty; correct must be a, b, c or d (found 'x'); "
                                     "set must be blank or one of a, b, c, d (found 'z')")

    def test_a_short_row_reports_its_missing_cells(self):
        errors = parse_question_csv(csv_text("T,Q,1,2\n"))[1]
        assert "choice c is empty" in errors[0].message and "choice d is empty" in errors[0].message

    @pytest.mark.parametrize("label", ["2/5/2026", "10/21/26", "2026-02-05", "2026-02-05 00:00:00", "5-Feb", "5-Feb-26"])
    def test_answers_a_spreadsheet_turned_into_dates_are_rejected(self, label):
        errors = parse_question_csv(csv_text(f"T,Q,{label},2,3,4,a,\n"))[1]
        assert "choice a" in errors[0].message and "looks like a date" in errors[0].message

    @pytest.mark.parametrize("label", ["2/5", "10/21", "13/21", "18/100", "(0.08, 7.92)", "1.5", "120", "95% of individuals"])
    def test_real_answers_are_not_mistaken_for_dates(self, label):
        assert parse_question_csv(csv_text(f'T,Q,"{label}",2,3,4,a,\n'))[1] == []

    def test_files_are_capped(self):
        rows = "".join(f"T{i},Q,1,2,3,4,a,\n" for i in range(MAX_IMPORT_ROWS + 5))
        questions, errors, count = parse_question_csv(csv_text(rows))
        assert len(questions) == MAX_IMPORT_ROWS
        assert errors[-1].row == MAX_IMPORT_ROWS + 2 and f"at most {MAX_IMPORT_ROWS}" in errors[-1].message

    def test_unreadable_csv_is_reported_not_raised(self, monkeypatch):
        import csv
        from app.services import questions as service

        class Broken:
            line_num = 3
            def __init__(self, rows):
                self.rows = iter(rows)
            def __iter__(self):
                return self
            def __next__(self):
                row = next(self.rows)
                if row is None:
                    raise csv.Error("new-line character seen in unquoted field")
                return row

        header = HEADER.strip().split(",")
        monkeypatch.setattr(service.csv, "reader", lambda _: Broken([header, ROW.strip().split(","), None]))
        questions, errors, _ = parse_question_csv("ignored")
        assert len(questions) == 1
        assert [(e.row, e.message) for e in errors] == [
            (3, "The file is not valid CSV: new-line character seen in unquoted field")]


class TestImportQuestions:
    def test_a_dry_run_reports_without_saving(self, bank):
        report = import_questions(bank, csv_text(ROW, "T,Q,1,2,3,4,a,\n"))
        assert report.dry_run and report.valid
        assert (report.rows, report.to_import, report.imported) == (2, 2, 0)
        assert report.by_set == {"a": 0, "b": 0, "c": 1, "d": 0, "unassigned": 1}
        assert bank.count_documents({}) == 0

    def test_an_import_saves_new_unjudged_questions(self, bank):
        report = import_questions(bank, csv_text(ROW), dry_run=False)
        assert report.imported == 1
        doc = bank.find_one({})
        assert doc["stem"] == "Basic Probability" and doc["set"] == "c" and doc["correct_choice_id"] == "b"
        assert doc["choices"] == [{"id": "a", "label": "2/5"}, {"id": "b", "label": "3/5"},
                                  {"id": "c", "label": "1/6"}, {"id": "d", "label": "2/3"}]
        # Difficulty is left for the "Judge difficulty" button.
        assert (doc["difficulty"], doc["difficulty_source"], doc["difficulty_checked"]) == (None, None, False)
        assert doc["active"] is True and doc["created_at"]

    def test_any_row_error_blocks_the_whole_file(self, bank):
        report = import_questions(bank, csv_text(ROW, "T,Q,1,2,3,4,z,\n"), dry_run=False)
        assert not report.valid and report.imported == 0 and report.to_import == 1
        assert bank.count_documents({}) == 0

    def test_questions_already_in_the_bank_are_skipped_with_a_note(self, bank):
        import_questions(bank, csv_text(ROW), dry_run=False)
        # Same question with different case and spacing.
        again = "basic   probability,a jar contains 4 RED and 6 blue,2/5,3/5,1/6,2/3,b,a\n"
        report = import_questions(bank, csv_text(again, "T,Q,1,2,3,4,a,\n"), dry_run=False)
        assert report.valid and report.imported == 1
        assert [(s.row, s.message) for s in report.skipped] == [(2, "Already in the question bank; skipped")]
        assert bank.count_documents({}) == 2

    def test_repeated_rows_within_the_file_are_imported_once(self, bank):
        report = import_questions(bank, csv_text(ROW, "T,Q,1,2,3,4,a,\n", ROW), dry_run=False)
        assert report.imported == 2
        assert [(s.row, s.message) for s in report.skipped] == [(4, "Same question as row 2; skipped")]

    def test_a_question_added_by_hand_counts_as_a_duplicate(self, bank):
        create_question(bank, QuestionCreate(stem="T", subtitle="Q", correct_choice_id="a", choices=[
            QuestionChoice(id=letter, label=label) for letter, label in zip("abcd", "1234")]))
        report = import_questions(bank, csv_text("T,Q,1,2,3,4,b,\n"))
        assert report.to_import == 0 and report.skipped[0].message == "Already in the question bank; skipped"

    def test_different_answers_are_not_duplicates(self, bank):
        import_questions(bank, csv_text("T,Q,1,2,3,4,a,\n"), dry_run=False)
        assert import_questions(bank, csv_text("T,Q,1,2,3,5,a,\n")).to_import == 1

    def test_legacy_questions_with_two_choices_do_not_break_the_check(self, bank):
        bank.insert_one({"stem": "Old", "choices": [{"id": "a", "label": "x"}, {"id": "b", "label": "y"}]})
        assert import_questions(bank, csv_text(ROW)).to_import == 1

    def test_a_file_of_only_duplicates_imports_nothing(self, bank):
        import_questions(bank, csv_text(ROW), dry_run=False)
        report = import_questions(bank, csv_text(ROW), dry_run=False)
        assert report.valid and report.imported == 0 and len(report.skipped) == 1


class TestImportQuestionsEndpoint:
    def _client(self, user, bank):
        app = FastAPI()
        app.include_router(questions_router)
        app.state.db = bank.database
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    def test_preview_then_import(self, admin_user, bank):
        client = self._client(admin_user, bank)
        preview = client.post("/questions/import", json={"csv": csv_text(ROW)})
        assert preview.status_code == 200
        assert preview.json()["dry_run"] is True and preview.json()["to_import"] == 1
        assert bank.count_documents({}) == 0
        done = client.post("/questions/import", json={"csv": csv_text(ROW), "dry_run": False}).json()
        assert done["imported"] == 1 and bank.count_documents({}) == 1
        listed = client.get("/questions").json()
        assert listed[0]["set"] == "c" and listed[0]["difficulty"] is None

    def test_errors_come_back_by_row(self, admin_user, bank):
        client = self._client(admin_user, bank)
        body = client.post("/questions/import", json={"csv": csv_text("T,Q,1,2,3,4,z,\n"), "dry_run": False}).json()
        assert body["valid"] is False and body["imported"] == 0
        assert body["errors"] == [{"row": 2, "message": "correct must be a, b, c or d (found 'z')"}]

    def test_non_admins_cannot_import(self, regular_user, bank):
        client = self._client(regular_user, bank)
        assert client.post("/questions/import", json={"csv": csv_text(ROW), "dry_run": False}).status_code == 403
        assert bank.count_documents({}) == 0

    def test_oversized_uploads_are_refused(self, admin_user, bank):
        client = self._client(admin_user, bank)
        assert client.post("/questions/import", json={"csv": "x" * 2_000_001}).status_code == 422

    def test_the_csv_text_is_required(self, admin_user, bank):
        client = self._client(admin_user, bank)
        assert client.post("/questions/import", json={}).status_code == 422
