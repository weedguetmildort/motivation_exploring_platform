# backend/tests/test_quiz_api.py
"""FastAPI TestClient integration tests for app/api/quiz.py."""
from datetime import datetime
from unittest.mock import MagicMock, patch
from bson import ObjectId
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.quiz import router as quiz_router
from app.api.auth import get_current_user
from app.schemas.user import UserPublic


# ── Local app fixtures (do not touch conftest.py) ────────────────────────────

@pytest.fixture
def admin_user_oid():
    """An admin user whose id is a valid ObjectId hex string.

    Needed for endpoints (like /reset) that pass user.id through
    bson.ObjectId(...).
    """
    return UserPublic(id=str(ObjectId()), email="admin@test.edu", is_admin=True)


@pytest.fixture
def quiz_app(admin_user, mock_db):
    app = FastAPI()
    app.include_router(quiz_router)
    app.state.db = mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return app


@pytest.fixture
def quiz_client(quiz_app):
    return TestClient(quiz_app)


@pytest.fixture
def quiz_app_oid(admin_user_oid, mock_db):
    app = FastAPI()
    app.include_router(quiz_router)
    app.state.db = mock_db
    app.dependency_overrides[get_current_user] = lambda: admin_user_oid
    return app


@pytest.fixture
def quiz_client_oid(quiz_app_oid, admin_user_oid):
    client = TestClient(quiz_app_oid)
    client.admin_id = admin_user_oid.id
    return client


@pytest.fixture
def regular_quiz_app(regular_user, mock_db):
    app = FastAPI()
    app.include_router(quiz_router)
    app.state.db = mock_db
    app.dependency_overrides[get_current_user] = lambda: regular_user
    return app


@pytest.fixture
def regular_quiz_client(regular_quiz_app):
    return TestClient(regular_quiz_app)


# ── GET /quiz/{quiz_id}/state ────────────────────────────────────────────────

class TestGetQuizState:
    def test_returns_in_progress_state_with_current_question(self, regular_quiz_client, mock_col):
        qid1 = ObjectId()
        qid2 = ObjectId()
        attempt_id = ObjectId()

        existing_attempt = {
            "_id": attempt_id,
            "user_id": "userid1",
            "user_email": "student@test.edu",
            "quiz_id": "base",
            "conversation_id": "conv-1",
            "status": "in_progress",
            "question_order": [str(qid1), str(qid2)],
            "incorrect_question_ids": [],
            "answers": [],
        }

        # _load_or_create_attempt -> finds existing attempt
        # build_quiz_state_response -> qcol.find(...) for existing ids
        # qcol.find_one -> next question doc
        # record_question_shown -> col.find_one (re-fetch updated doc)
        # build_quiz_state_response (second pass) -> qcol.find again, qcol.find_one again

        question_doc = {
            "_id": qid1,
            "stem": "What is 2+2?",
            "subtitle": None,
            "choices": [{"id": "a", "label": "3"}, {"id": "b", "label": "4"}],
        }

        updated_attempt = {**existing_attempt, "answers": [
            {"question_id": str(qid1), "shown_at": datetime.utcnow(), "answered_at": None, "choice_id": None}
        ]}

        # find_one is called on both quiz_attempts collection and questions collection,
        # but mock_db routes both to the same mock_col. Order of find_one calls:
        # 1. _load_or_create_attempt: col.find_one (attempt lookup) -> existing_attempt
        # 2. build_quiz_state_response #1: qcol.find_one (next question) -> question_doc
        # 3. record_question_shown: col.find_one (re-fetch) -> updated_attempt
        # 4. build_quiz_state_response #2: qcol.find_one (next question) -> question_doc
        mock_col.find_one.side_effect = [existing_attempt, question_doc, updated_attempt, question_doc]
        mock_col.find.return_value = [{"_id": qid1}, {"_id": qid2}]

        resp = regular_quiz_client.get("/quiz/base/state")

        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_id"] == "conv-1"
        assert data["attempt"]["quiz_id"] == "base"
        assert data["attempt"]["status"] == "in_progress"
        assert data["attempt"]["total_questions"] == 2
        assert data["current_question"]["id"] == str(qid1)
        assert data["current_question"]["stem"] == "What is 2+2?"

    def test_returns_completed_state_without_current_question(self, regular_quiz_client, mock_col):
        attempt_id = ObjectId()
        now = datetime.utcnow()
        completed_attempt = {
            "_id": attempt_id,
            "user_id": "userid1",
            "user_email": "student@test.edu",
            "quiz_id": "base",
            "conversation_id": "conv-2",
            "status": "completed",
            "question_order": ["q1", "q2"],
            "incorrect_question_ids": ["q1"],
            "answers": [
                {"question_id": "q1", "answered_at": now},
                {"question_id": "q2", "answered_at": now},
            ],
        }
        mock_col.find_one.return_value = completed_attempt

        resp = regular_quiz_client.get("/quiz/base/state")

        assert resp.status_code == 200
        data = resp.json()
        assert data["attempt"]["status"] == "completed"
        assert data["attempt"]["total_questions"] == 2
        assert data["attempt"]["answered_count"] == 2
        assert data["current_question"] is None
        assert data["attempt"]["incorrect_question_ids"] == ["q1"]

    def test_no_questions_available_returns_400(self, regular_quiz_client, mock_col):
        # No existing attempt, and no questions in the questions collection.
        mock_col.find_one.return_value = None
        mock_col.find.return_value = []

        resp = regular_quiz_client.get("/quiz/base/state")

        assert resp.status_code == 400
        assert "No questions available" in resp.json()["detail"]

    def test_creates_new_attempt_when_none_exists(self, regular_quiz_client, mock_col):
        qid1 = ObjectId()
        inserted_id = ObjectId()

        question_doc = {
            "_id": qid1,
            "stem": "Q1",
            "subtitle": None,
            "choices": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        }

        # _load_or_create_attempt: col.find_one -> None (no existing attempt)
        #                          qcol.find({}, {"_id": 1}) -> [{"_id": qid1}]
        #                          col.insert_one -> inserted_id
        # build_quiz_state_response #1: qcol.find(...) -> existing ids; qcol.find_one -> question_doc
        # record_question_shown: col.find_one -> updated doc
        # build_quiz_state_response #2: qcol.find(...) -> existing ids; qcol.find_one -> question_doc

        created_doc_holder = {}

        def find_one_side_effect(*args, **kwargs):
            query = args[0] if args else kwargs.get("filter", {})
            if "user_id" in query and "quiz_id" in query:
                # quiz_attempts lookup
                if not created_doc_holder:
                    return None
                return created_doc_holder["doc"]
            # questions/attempts lookup by _id
            if query.get("_id") == qid1:
                return question_doc
            if query.get("_id") == inserted_id:
                return created_doc_holder.get("doc")
            return None

        mock_col.find_one.side_effect = find_one_side_effect
        mock_col.find.return_value = [{"_id": qid1}]

        def insert_one_side_effect(doc):
            doc["_id"] = inserted_id
            created_doc_holder["doc"] = {**doc, "answers": []}
            return MagicMock(inserted_id=inserted_id)

        mock_col.insert_one.side_effect = insert_one_side_effect

        with patch("random.shuffle", side_effect=lambda lst: None), \
                patch("random.sample", return_value=[str(qid1)]):
            resp = regular_quiz_client.get("/quiz/base/state")

        assert resp.status_code == 200
        data = resp.json()
        assert data["attempt"]["quiz_id"] == "base"
        assert data["current_question"]["id"] == str(qid1)


# ── POST /quiz/{quiz_id}/answer ──────────────────────────────────────────────

class TestSubmitQuizAnswer:
    def test_submit_correct_answer(self, regular_quiz_client, mock_col):
        attempt_id = ObjectId()
        qid1 = ObjectId()
        qid2 = ObjectId()

        attempt_doc = {
            "_id": attempt_id,
            "user_id": "userid1",
            "quiz_id": "base",
            "conversation_id": "conv-1",
            "status": "in_progress",
            "question_order": [str(qid1), str(qid2)],
            "incorrect_question_ids": [],
            "answers": [
                {"question_id": str(qid1), "shown_at": datetime.utcnow(), "answered_at": None, "choice_id": None}
            ],
        }
        question_doc = {"_id": qid1, "correct_choice_id": "a"}
        next_question_doc = {
            "_id": qid2,
            "stem": "Q2",
            "subtitle": None,
            "choices": [{"id": "a", "label": "X"}, {"id": "b", "label": "Y"}],
        }

        updated_doc = {
            **attempt_doc,
            "answers": [
                {"question_id": str(qid1), "shown_at": datetime.utcnow(), "answered_at": datetime.utcnow(), "choice_id": "a", "marked_correct": True}
            ],
        }

        # record_answer: find_one(attempt) -> attempt_doc
        #                find_one(question, correct_choice_id) -> question_doc
        #                update_one (positional $set) -> matched_count=1
        #                find_one(updated attempt) -> updated_doc
        # build_quiz_state_response: qcol.find(...) -> existing ids; qcol.find_one(next q) -> next_question_doc
        mock_col.find_one.side_effect = [attempt_doc, question_doc, updated_doc, next_question_doc]
        mock_col.update_one.return_value = MagicMock(matched_count=1)
        mock_col.find.return_value = [{"_id": qid1}, {"_id": qid2}]

        resp = regular_quiz_client.post(
            "/quiz/base/answer",
            json={"question_id": str(qid1), "choice_id": "a"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["current_question"]["id"] == str(qid2)

    def test_no_attempt_returns_400(self, regular_quiz_client, mock_col):
        mock_col.find_one.return_value = None

        resp = regular_quiz_client.post(
            "/quiz/base/answer",
            json={"question_id": str(ObjectId()), "choice_id": "a"},
        )

        assert resp.status_code == 400
        assert "No quiz attempt found" in resp.json()["detail"]

    def test_already_completed_returns_400(self, regular_quiz_client, mock_col):
        mock_col.find_one.return_value = {
            "_id": ObjectId(),
            "status": "completed",
            "question_order": [],
        }

        resp = regular_quiz_client.post(
            "/quiz/base/answer",
            json={"question_id": str(ObjectId()), "choice_id": "a"},
        )

        assert resp.status_code == 400
        assert "already completed" in resp.json()["detail"]

    def test_question_not_in_attempt_returns_400(self, regular_quiz_client, mock_col):
        mock_col.find_one.return_value = {
            "_id": ObjectId(),
            "status": "in_progress",
            "question_order": ["some-other-qid"],
        }

        resp = regular_quiz_client.post(
            "/quiz/base/answer",
            json={"question_id": str(ObjectId()), "choice_id": "a"},
        )

        assert resp.status_code == 400
        assert "not part of this quiz" in resp.json()["detail"]

    def test_missing_fields_returns_422(self, regular_quiz_client):
        resp = regular_quiz_client.post("/quiz/base/answer", json={"question_id": "abc"})
        assert resp.status_code == 422

    def test_invalid_body_type_returns_422(self, regular_quiz_client):
        resp = regular_quiz_client.post(
            "/quiz/base/answer",
            json={"question_id": 123, "choice_id": "a"},
        )
        assert resp.status_code == 422


# ── GET /quiz/{quiz_id}/results (admin only) ─────────────────────────────────

class TestGetQuizResultsEndpoint:
    def test_admin_can_get_results(self, quiz_client, mock_col):
        qid1 = ObjectId()
        now = datetime.utcnow()

        attempt_doc = {
            "_id": ObjectId(),
            "question_order": [str(qid1)],
            "answers": [
                {"question_id": str(qid1), "answered_at": now, "choice_id": "a", "marked_correct": True},
            ],
        }
        question_doc = {
            "_id": qid1,
            "stem": "Q1",
            "choices": [{"id": "a", "label": "Correct"}, {"id": "b", "label": "Wrong"}],
            "correct_choice_id": "a",
        }

        def find_one_side_effect(query, *args, **kwargs):
            if "_id" in query:
                return question_doc
            return attempt_doc

        mock_col.find_one.side_effect = find_one_side_effect

        resp = quiz_client.get("/quiz/base/results")

        assert resp.status_code == 200
        data = resp.json()
        assert data["quiz_id"] == "base"
        assert data["total_questions"] == 1
        assert data["correct_count"] == 1
        assert data["items"][0]["is_correct"] is True

    def test_non_admin_forbidden(self, regular_quiz_client):
        resp = regular_quiz_client.get("/quiz/base/results")
        assert resp.status_code == 403

    def test_no_attempt_returns_404(self, quiz_client, mock_col):
        mock_col.find_one.return_value = None

        resp = quiz_client.get("/quiz/base/results")

        assert resp.status_code == 404
        assert "No quiz attempt found" in resp.json()["detail"]


# ── POST /quiz/{quiz_id}/reset (admin only) ──────────────────────────────────

class TestResetQuiz:
    def test_admin_can_reset(self, quiz_client_oid, mock_col):
        resp = quiz_client_oid.post("/quiz/base/reset")

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_col.delete_one.assert_called_once_with({"user_id": quiz_client_oid.admin_id, "quiz_id": "base"})

    def test_non_admin_forbidden(self, regular_quiz_client, mock_col):
        resp = regular_quiz_client.post("/quiz/base/reset")
        assert resp.status_code == 403
        mock_col.delete_one.assert_not_called()

    def test_reset_variant_quiz_updates_user_flags(self, quiz_client_oid, mock_col):
        resp = quiz_client_oid.post("/quiz/followup/reset")

        assert resp.status_code == 200
        mock_col.delete_one.assert_called_once_with({"user_id": quiz_client_oid.admin_id, "quiz_id": "followup"})
        update_call = mock_col.update_one.call_args
        assert update_call[0][1]["$set"]["quiz_variant_completed"] is False

    def test_reset_unknown_quiz_id_only_deletes(self, quiz_client_oid, mock_col):
        resp = quiz_client_oid.post("/quiz/some-unknown-id/reset")

        assert resp.status_code == 200
        mock_col.delete_one.assert_called_once_with({"user_id": quiz_client_oid.admin_id, "quiz_id": "some-unknown-id"})
        mock_col.update_one.assert_not_called()
