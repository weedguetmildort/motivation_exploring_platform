# backend/tests/test_quiz_service.py
"""Unit tests for app/services/quiz.py."""
from datetime import datetime
from unittest.mock import MagicMock, patch
from bson import ObjectId
import pytest
from fastapi import HTTPException

from app.services.quiz import (
    get_users_collection,
    get_quiz_attempts_collection,
    _ensure_unique_index,
    _load_or_create_attempt,
    _find_next_unanswered,
    _mark_quiz_completed,
    _get_user_quiz_update_fields,
    reset_quiz_attempt,
    build_quiz_state_response,
    record_question_shown,
    record_answer,
    get_quiz_results,
    MAX_QUIZ_QUESTIONS,
)
from app.schemas.user import SurveyStage


# ── get_users_collection / get_quiz_attempts_collection ─────────────────────

class TestCollectionAccessors:
    def test_get_users_collection(self, mock_db, mock_col):
        assert get_users_collection(mock_db) is mock_col
        mock_db.__getitem__.assert_any_call("users")

    def test_get_quiz_attempts_collection(self, mock_db, mock_col):
        assert get_quiz_attempts_collection(mock_db) is mock_col
        mock_db.__getitem__.assert_any_call("quiz_attempts")

    def test_ensure_unique_index_calls_create_index(self):
        col = MagicMock()
        _ensure_unique_index(col)
        col.create_index.assert_called_once_with(
            [("user_id", 1), ("quiz_id", 1)], unique=True
        )


# ── _load_or_create_attempt ──────────────────────────────────────────────────

class TestLoadOrCreateAttempt:
    def test_returns_existing_attempt(self, mock_db, mock_col):
        existing = {"_id": ObjectId(), "user_id": "u1", "quiz_id": "base", "status": "in_progress"}
        mock_col.find_one.return_value = existing

        result = _load_or_create_attempt(mock_db, "u1", "u1@test.edu", "base")

        assert result is existing
        mock_col.create_index.assert_called_once()
        mock_col.insert_one.assert_not_called()

    def test_no_questions_raises_400(self, mock_db, mock_col):
        mock_col.find_one.return_value = None
        # questions collection .find({}, {"_id": 1}) returns empty
        mock_col.find.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            _load_or_create_attempt(mock_db, "u1", "u1@test.edu", "base")

        assert exc_info.value.status_code == 400
        assert "No questions available" in exc_info.value.detail

    def test_creates_new_attempt_with_shuffled_questions(self, mock_db, mock_col):
        mock_col.find_one.return_value = None

        question_ids = [ObjectId() for _ in range(5)]
        mock_col.find.return_value = [{"_id": qid} for qid in question_ids]

        inserted_id = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=inserted_id)

        with patch("random.shuffle") as mock_shuffle, \
                patch("random.sample") as mock_sample:
            # shuffle is in-place; leave list unchanged
            mock_shuffle.side_effect = lambda lst: None
            mock_sample.return_value = [str(question_ids[0]), str(question_ids[1])]

            result = _load_or_create_attempt(mock_db, "u1", "u1@test.edu", "base")

        assert result["user_id"] == "u1"
        assert result["user_email"] == "u1@test.edu"
        assert result["quiz_id"] == "base"
        assert result["status"] == "in_progress"
        assert result["answers"] == []
        assert result["_id"] == inserted_id
        assert set(result["question_order"]) == {str(qid) for qid in question_ids}
        assert result["incorrect_question_ids"] == [str(question_ids[0]), str(question_ids[1])]
        assert "conversation_id" in result
        mock_col.insert_one.assert_called_once()

    def test_question_order_capped_at_max(self, mock_db, mock_col):
        mock_col.find_one.return_value = None

        question_ids = [ObjectId() for _ in range(MAX_QUIZ_QUESTIONS + 5)]
        mock_col.find.return_value = [{"_id": qid} for qid in question_ids]
        mock_col.insert_one.return_value = MagicMock(inserted_id=ObjectId())

        # use real random so we exercise the actual shuffle/sample logic
        result = _load_or_create_attempt(mock_db, "u1", "u1@test.edu", "base")

        assert len(result["question_order"]) == MAX_QUIZ_QUESTIONS
        assert len(result["incorrect_question_ids"]) == 3
        # incorrect ids must be a subset of the question order
        assert set(result["incorrect_question_ids"]).issubset(set(result["question_order"]))

    def test_incorrect_ids_capped_when_fewer_than_three_questions(self, mock_db, mock_col):
        mock_col.find_one.return_value = None
        question_ids = [ObjectId(), ObjectId()]
        mock_col.find.return_value = [{"_id": qid} for qid in question_ids]
        mock_col.insert_one.return_value = MagicMock(inserted_id=ObjectId())

        result = _load_or_create_attempt(mock_db, "u1", "u1@test.edu", "base")

        assert len(result["question_order"]) == 2
        assert len(result["incorrect_question_ids"]) == 2


# ── _find_next_unanswered ─────────────────────────────────────────────────────

class TestFindNextUnanswered:
    def test_returns_first_unanswered(self):
        doc = {
            "question_order": ["q1", "q2", "q3"],
            "answers": [
                {"question_id": "q1", "answered_at": datetime.utcnow()},
            ],
        }
        assert _find_next_unanswered(doc) == "q2"

    def test_all_answered_returns_none(self):
        now = datetime.utcnow()
        doc = {
            "question_order": ["q1", "q2"],
            "answers": [
                {"question_id": "q1", "answered_at": now},
                {"question_id": "q2", "answered_at": now},
            ],
        }
        assert _find_next_unanswered(doc) is None

    def test_unanswered_record_with_no_answered_at_is_skipped_check(self):
        # an "answers" entry without answered_at should NOT count as answered
        doc = {
            "question_order": ["q1"],
            "answers": [
                {"question_id": "q1", "answered_at": None},
            ],
        }
        assert _find_next_unanswered(doc) == "q1"

    def test_empty_question_order_returns_none(self):
        doc = {"question_order": [], "answers": []}
        assert _find_next_unanswered(doc) is None

    def test_skips_deleted_questions_when_qcol_provided(self):
        qid_exists = str(ObjectId())
        qid_deleted = str(ObjectId())
        doc = {
            "question_order": [qid_deleted, qid_exists],
            "answers": [],
        }
        qcol = MagicMock()

        def count_documents(query, limit=None):
            oid = query["_id"]
            return 0 if str(oid) == qid_deleted else 1

        qcol.count_documents.side_effect = count_documents

        assert _find_next_unanswered(doc, qcol) == qid_exists

    def test_no_qcol_does_not_check_existence(self):
        qid = str(ObjectId())
        doc = {"question_order": [qid], "answers": []}
        assert _find_next_unanswered(doc, None) == qid


# ── _get_user_quiz_update_fields ─────────────────────────────────────────────

class TestGetUserQuizUpdateFields:
    def test_base_quiz(self):
        completed_at = datetime.utcnow()
        result = _get_user_quiz_update_fields("base", completed_at)
        assert result["quiz_base_completed"] is True
        assert result["survey_stage"] == SurveyStage.post_base.value
        assert result["updated_at"] == completed_at

    def test_variant_quiz(self):
        completed_at = datetime.utcnow()
        result = _get_user_quiz_update_fields("followup", completed_at)
        assert result["quiz_variant_completed"] is True
        assert result["survey_stage"] == SurveyStage.post_variant.value
        assert result["updated_at"] == completed_at

    def test_unknown_quiz_id(self):
        completed_at = datetime.utcnow()
        result = _get_user_quiz_update_fields("some-admin-test", completed_at)
        assert result == {"updated_at": completed_at}
        assert "quiz_base_completed" not in result
        assert "quiz_variant_completed" not in result


# ── _mark_quiz_completed ───────────────────────────────────────────────────────

class TestMarkQuizCompleted:
    def test_marks_completed_and_updates_user(self, mock_db, mock_col):
        doc = {"_id": ObjectId(), "quiz_id": "base", "user_id": str(ObjectId())}
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        _mark_quiz_completed(mock_db, doc)

        # First call updates the attempt status
        first_call = mock_col.update_one.call_args_list[0]
        assert first_call[0][0] == {"_id": doc["_id"]}
        assert first_call[0][1]["$set"]["status"] == "completed"

        # Second call updates the user
        second_call = mock_col.update_one.call_args_list[1]
        assert second_call[0][1]["$set"]["quiz_base_completed"] is True

    def test_user_not_found_raises_404(self, mock_db, mock_col):
        doc = {"_id": ObjectId(), "quiz_id": "base", "user_id": str(ObjectId())}
        mock_col.update_one.return_value = MagicMock(matched_count=0)

        with pytest.raises(HTTPException) as exc_info:
            _mark_quiz_completed(mock_db, doc)

        assert exc_info.value.status_code == 404


# ── reset_quiz_attempt ────────────────────────────────────────────────────────

class TestResetQuizAttempt:
    def test_reset_base_quiz(self, mock_db, mock_col):
        user_id = str(ObjectId())
        reset_quiz_attempt(mock_db, user_id, "base")

        mock_col.delete_one.assert_called_once_with({"user_id": user_id, "quiz_id": "base"})
        # user update called with reverted flags
        update_call = mock_col.update_one.call_args
        assert update_call[0][1]["$set"]["quiz_base_completed"] is False
        assert update_call[0][1]["$set"]["survey_stage"] == SurveyStage.pre_base.value

    def test_reset_variant_quiz(self, mock_db, mock_col):
        user_id = str(ObjectId())
        reset_quiz_attempt(mock_db, user_id, "followup")

        mock_col.delete_one.assert_called_once_with({"user_id": user_id, "quiz_id": "followup"})
        update_call = mock_col.update_one.call_args
        assert update_call[0][1]["$set"]["quiz_variant_completed"] is False
        assert update_call[0][1]["$set"]["survey_stage"] == SurveyStage.post_base.value

    def test_reset_unknown_quiz_id_only_deletes(self, mock_db, mock_col):
        user_id = str(ObjectId())
        reset_quiz_attempt(mock_db, user_id, "unknown-quiz")

        mock_col.delete_one.assert_called_once_with({"user_id": user_id, "quiz_id": "unknown-quiz"})
        # update_one should NOT be called for unknown quiz ids
        mock_col.update_one.assert_not_called()


# ── build_quiz_state_response ────────────────────────────────────────────────

class TestBuildQuizStateResponse:
    def test_completed_quiz_returns_no_current_question(self, mock_db, mock_col):
        now = datetime.utcnow()
        doc = {
            "_id": ObjectId(),
            "quiz_id": "base",
            "status": "completed",
            "conversation_id": "conv-123",
            "question_order": ["q1", "q2"],
            "answers": [
                {"question_id": "q1", "answered_at": now},
                {"question_id": "q2", "answered_at": now},
            ],
            "incorrect_question_ids": ["q1"],
        }

        result = build_quiz_state_response(mock_db, doc)

        assert result.conversation_id == "conv-123"
        assert result.attempt.status == "completed"
        assert result.attempt.total_questions == 2
        assert result.attempt.answered_count == 2
        assert result.attempt.incorrect_question_ids == ["q1"]
        assert result.current_question is None

    def test_in_progress_returns_current_question(self, mock_db, mock_col):
        qid1 = ObjectId()
        qid2 = ObjectId()
        doc = {
            "_id": ObjectId(),
            "quiz_id": "base",
            "status": "in_progress",
            "conversation_id": "conv-456",
            "question_order": [str(qid1), str(qid2)],
            "answers": [],
            "incorrect_question_ids": [],
        }

        # qcol.find(...) returns existing question ids
        mock_col.find.return_value = [{"_id": qid1}, {"_id": qid2}]
        # qcol.find_one returns the next question doc
        mock_col.find_one.return_value = {
            "_id": qid1,
            "stem": "What is 2+2?",
            "subtitle": "Math basics",
            "choices": [{"id": "a", "label": "3"}, {"id": "b", "label": "4"}],
        }

        result = build_quiz_state_response(mock_db, doc)

        assert result.conversation_id == "conv-456"
        assert result.attempt.status == "in_progress"
        assert result.attempt.total_questions == 2
        assert result.attempt.answered_count == 0
        assert result.current_question is not None
        assert result.current_question.id == str(qid1)
        assert result.current_question.stem == "What is 2+2?"
        assert result.current_question.choices == [{"id": "a", "label": "3"}, {"id": "b", "label": "4"}]

    def test_in_progress_with_no_unanswered_marks_completed(self, mock_db, mock_col):
        now = datetime.utcnow()
        qid1 = ObjectId()
        doc_id = ObjectId()
        user_id = ObjectId()
        doc = {
            "_id": doc_id,
            "quiz_id": "base",
            "user_id": str(user_id),
            "status": "in_progress",
            "conversation_id": "conv-789",
            "question_order": [str(qid1)],
            "answers": [
                {"question_id": str(qid1), "answered_at": now},
            ],
            "incorrect_question_ids": [],
        }

        # All questions still exist
        mock_col.find.return_value = [{"_id": qid1}]
        # update_one used for marking completed (attempts) and user update
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        result = build_quiz_state_response(mock_db, doc)

        assert result.attempt.status == "completed"
        assert result.current_question is None
        assert result.attempt.total_questions == 1
        assert result.attempt.answered_count == 1
        # ensure attempt status update was issued
        mock_col.update_one.assert_any_call(
            {"_id": doc_id},
            {"$set": {"status": "completed", "updated_at": mock_col.update_one.call_args_list[0][0][1]["$set"]["updated_at"]}},
        )

    def test_next_question_deleted_race_condition_marks_completed(self, mock_db, mock_col):
        """If _find_next_unanswered finds an id but find_one returns None
        (race condition), the quiz should be marked completed."""
        qid1 = ObjectId()
        doc_id = ObjectId()
        user_id = ObjectId()
        doc = {
            "_id": doc_id,
            "quiz_id": "base",
            "user_id": str(user_id),
            "status": "in_progress",
            "conversation_id": "conv-999",
            "question_order": [str(qid1)],
            "answers": [],
            "incorrect_question_ids": [],
        }

        # Existing-ids check (qcol.find) returns the question still existing...
        mock_col.find.return_value = [{"_id": qid1}]
        # ...but count_documents (used by _find_next_unanswered) says it exists,
        # while find_one (fetching the full doc) returns None -- race condition.
        mock_col.count_documents.return_value = 1
        mock_col.find_one.return_value = None
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        result = build_quiz_state_response(mock_db, doc)

        assert result.attempt.status == "completed"
        assert result.current_question is None

    def test_filters_out_deleted_questions_from_totals(self, mock_db, mock_col):
        """Questions removed from the DB shouldn't count toward total/answered."""
        now = datetime.utcnow()
        qid_existing = ObjectId()
        qid_deleted = ObjectId()
        doc = {
            "_id": ObjectId(),
            "quiz_id": "base",
            "user_id": str(ObjectId()),
            "status": "in_progress",
            "conversation_id": "conv-abc",
            "question_order": [str(qid_existing), str(qid_deleted)],
            "answers": [
                {"question_id": str(qid_existing), "answered_at": now},
                {"question_id": str(qid_deleted), "answered_at": now},
            ],
            "incorrect_question_ids": [],
        }

        # only qid_existing remains in the questions collection
        mock_col.find.return_value = [{"_id": qid_existing}]
        mock_col.count_documents.return_value = 1
        mock_col.find_one.return_value = {
            "_id": qid_existing,
            "stem": "Q",
            "subtitle": None,
            "choices": [],
        }
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        result = build_quiz_state_response(mock_db, doc)

        # total/answered should only reflect the existing question (already answered)
        assert result.attempt.total_questions == 1
        assert result.attempt.answered_count == 1
        # Both questions in question_order are "answered" -> quiz auto-completes
        assert result.attempt.status == "completed"


# ── record_question_shown ────────────────────────────────────────────────────

class TestRecordQuestionShown:
    def test_pushes_new_answer_record_when_not_present(self, mock_db, mock_col):
        doc_id = ObjectId()
        doc = {"_id": doc_id, "answers": []}
        updated_doc = {"_id": doc_id, "answers": [{"question_id": "q1", "shown_at": datetime.utcnow()}]}
        mock_col.find_one.return_value = updated_doc

        result = record_question_shown(mock_db, doc, "q1")

        mock_col.update_one.assert_called_once()
        call_args = mock_col.update_one.call_args
        assert call_args[0][0] == {"_id": doc_id}
        push = call_args[0][1]["$push"]["answers"]
        assert push["question_id"] == "q1"
        assert push["answered_at"] is None
        assert push["choice_id"] is None
        assert result is updated_doc

    def test_no_op_when_question_already_recorded(self, mock_db, mock_col):
        doc_id = ObjectId()
        doc = {
            "_id": doc_id,
            "answers": [{"question_id": "q1", "shown_at": datetime.utcnow(), "answered_at": None, "choice_id": None}],
        }

        result = record_question_shown(mock_db, doc, "q1")

        mock_col.update_one.assert_not_called()
        mock_col.find_one.assert_not_called()
        assert result is doc


# ── record_answer ─────────────────────────────────────────────────────────────

class TestRecordAnswer:
    def test_no_attempt_found_raises_400(self, mock_db, mock_col):
        mock_col.find_one.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            record_answer(mock_db, "u1", "base", "q1", "a")

        assert exc_info.value.status_code == 400
        assert "No quiz attempt found" in exc_info.value.detail

    def test_already_completed_raises_400(self, mock_db, mock_col):
        mock_col.find_one.return_value = {
            "_id": ObjectId(), "status": "completed", "question_order": ["q1"],
        }

        with pytest.raises(HTTPException) as exc_info:
            record_answer(mock_db, "u1", "base", "q1", "a")

        assert exc_info.value.status_code == 400
        assert "already completed" in exc_info.value.detail

    def test_question_not_in_attempt_raises_400(self, mock_db, mock_col):
        mock_col.find_one.return_value = {
            "_id": ObjectId(), "status": "in_progress", "question_order": ["q1", "q2"],
        }

        with pytest.raises(HTTPException) as exc_info:
            record_answer(mock_db, "u1", "base", "q-not-in-quiz", "a")

        assert exc_info.value.status_code == 400
        assert "not part of this quiz" in exc_info.value.detail

    def test_correct_answer_marked_correct_existing_record_updated(self, mock_db, mock_col):
        doc_id = ObjectId()
        qid = str(ObjectId())
        user_id = str(ObjectId())
        attempt_doc = {
            "_id": doc_id,
            "status": "in_progress",
            "user_id": user_id,
            "quiz_id": "base",
            "question_order": [qid],
            "answers": [{"question_id": qid, "shown_at": datetime.utcnow(), "answered_at": None, "choice_id": None}],
        }

        # This is the only question -> after answering, the quiz auto-completes.
        updated_doc = {
            "_id": doc_id,
            "status": "in_progress",
            "user_id": user_id,
            "quiz_id": "base",
            "question_order": [qid],
            "answers": [{"question_id": qid, "shown_at": datetime.utcnow(), "answered_at": datetime.utcnow(), "choice_id": "a", "marked_correct": True}],
        }
        completed_doc = {**updated_doc, "status": "completed"}

        # find_one sequence: attempt lookup, question lookup, post-update fetch, post-completion fetch
        mock_col.find_one.side_effect = [attempt_doc, {"correct_choice_id": "a"}, updated_doc, completed_doc]
        # found existing answer subdoc -> matched_count = 1, no completion needed
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        result = record_answer(mock_db, user_id, "base", qid, "a")

        # update_one called with $set for the matched subdocument
        first_update_call = mock_col.update_one.call_args_list[0]
        set_fields = first_update_call[0][1]["$set"]
        assert set_fields["answers.$.choice_id"] == "a"
        assert set_fields["answers.$.marked_correct"] is True
        assert result is completed_doc

    def test_incorrect_answer_marked_incorrect(self, mock_db, mock_col):
        doc_id = ObjectId()
        qid = str(ObjectId())
        attempt_doc = {
            "_id": doc_id,
            "status": "in_progress",
            "question_order": [qid],
            "answers": [{"question_id": qid, "shown_at": datetime.utcnow(), "answered_at": None, "choice_id": None}],
        }
        updated_doc = {**attempt_doc}

        mock_col.find_one.side_effect = [attempt_doc, {"correct_choice_id": "b"}, updated_doc]
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        record_answer(mock_db, "u1", "base", qid, "a")

        first_update_call = mock_col.update_one.call_args_list[0]
        set_fields = first_update_call[0][1]["$set"]
        assert set_fields["answers.$.marked_correct"] is False

    def test_answer_pushed_when_no_existing_record(self, mock_db, mock_col):
        """If the answers.$ positional update doesn't match (matched_count=0),
        a new answer record should be $push'd."""
        doc_id = ObjectId()
        qid = str(ObjectId())
        user_id = str(ObjectId())
        attempt_doc = {
            "_id": doc_id,
            "status": "in_progress",
            "user_id": user_id,
            "quiz_id": "base",
            "question_order": [qid],
            "answers": [],
        }
        # This is the only question -> after answering, the quiz auto-completes.
        updated_doc = {
            "_id": doc_id,
            "status": "in_progress",
            "user_id": user_id,
            "quiz_id": "base",
            "question_order": [qid],
            "answers": [{"question_id": qid, "shown_at": datetime.utcnow(), "answered_at": datetime.utcnow(), "choice_id": "a", "marked_correct": True}],
        }
        completed_doc = {**updated_doc, "status": "completed"}

        # find_one sequence: attempt lookup, question lookup, post-update fetch, post-completion fetch
        mock_col.find_one.side_effect = [attempt_doc, {"correct_choice_id": "a"}, updated_doc, completed_doc]
        # First update_one (positional) doesn't match -> matched_count = 0
        # Second update_one ($push) -> matched_count = 1
        # Third update_one (mark completed: attempt status) -> matched_count = 1
        # Fourth update_one (mark completed: user flags) -> matched_count = 1
        mock_col.update_one.side_effect = [
            MagicMock(matched_count=0),
            MagicMock(matched_count=1),
            MagicMock(matched_count=1),
            MagicMock(matched_count=1),
        ]

        result = record_answer(mock_db, user_id, "base", qid, "a")

        assert mock_col.update_one.call_count == 4
        push_call = mock_col.update_one.call_args_list[1]
        push_doc = push_call[0][1]["$push"]["answers"]
        assert push_doc["question_id"] == qid
        assert push_doc["choice_id"] == "a"
        assert push_doc["marked_correct"] is True
        assert result is completed_doc

    def test_question_not_found_in_questions_collection_marked_incorrect(self, mock_db, mock_col):
        """If the question doc can't be found (e.g. deleted), is_correct is False."""
        doc_id = ObjectId()
        qid = str(ObjectId())
        attempt_doc = {
            "_id": doc_id,
            "status": "in_progress",
            "question_order": [qid],
            "answers": [{"question_id": qid, "shown_at": datetime.utcnow(), "answered_at": None, "choice_id": None}],
        }
        updated_doc = {**attempt_doc}

        mock_col.find_one.side_effect = [attempt_doc, None, updated_doc]
        mock_col.update_one.return_value = MagicMock(matched_count=1)

        record_answer(mock_db, "u1", "base", qid, "a")

        first_update_call = mock_col.update_one.call_args_list[0]
        set_fields = first_update_call[0][1]["$set"]
        assert set_fields["answers.$.marked_correct"] is False

    def test_completes_quiz_when_last_question_answered(self, mock_db, mock_col):
        """When the answered question is the last unanswered one, the quiz
        should be marked completed and re-fetched."""
        doc_id = ObjectId()
        user_id = str(ObjectId())
        qid = str(ObjectId())
        attempt_doc = {
            "_id": doc_id,
            "status": "in_progress",
            "user_id": user_id,
            "quiz_id": "base",
            "question_order": [qid],
            "answers": [{"question_id": qid, "shown_at": datetime.utcnow(), "answered_at": None, "choice_id": None}],
        }
        now = datetime.utcnow()
        updated_doc_after_answer = {
            "_id": doc_id,
            "status": "in_progress",
            "user_id": user_id,
            "quiz_id": "base",
            "question_order": [qid],
            "answers": [{"question_id": qid, "shown_at": now, "answered_at": now, "choice_id": "a", "marked_correct": True}],
        }
        completed_doc = {**updated_doc_after_answer, "status": "completed"}

        # find_one sequence:
        # 1. attempt lookup
        # 2. question lookup (correct_choice_id)
        # 3. find_one after update -> "updated"
        # 4. find_one after marking completed -> "completed_doc"
        mock_col.find_one.side_effect = [attempt_doc, {"correct_choice_id": "a"}, updated_doc_after_answer, completed_doc]
        mock_col.update_one.return_value = MagicMock(matched_count=1)
        # _find_next_unanswered -> question_order has 1 item, which is now answered -> returns None
        # (count_documents not even reached because answered_map already filters it out)

        result = record_answer(mock_db, user_id, "base", qid, "a")

        assert result is completed_doc
        # _mark_quiz_completed should have triggered an update for status=completed
        completed_calls = [
            c for c in mock_col.update_one.call_args_list
            if c[0][1].get("$set", {}).get("status") == "completed"
        ]
        assert len(completed_calls) == 1


# ── get_quiz_results ──────────────────────────────────────────────────────────

class TestGetQuizResults:
    def test_no_attempt_raises_404(self, mock_db, mock_col):
        mock_col.find_one.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_quiz_results(mock_db, "u1", "base")

        assert exc_info.value.status_code == 404
        assert "No quiz attempt found" in exc_info.value.detail

    def test_returns_results_with_score(self, mock_db, mock_col):
        qid1 = ObjectId()
        qid2 = ObjectId()
        now = datetime.utcnow()

        attempt_doc = {
            "_id": ObjectId(),
            "question_order": [str(qid1), str(qid2)],
            "answers": [
                {"question_id": str(qid1), "answered_at": now, "choice_id": "a", "marked_correct": True},
                {"question_id": str(qid2), "answered_at": now, "choice_id": "b", "marked_correct": False},
            ],
        }

        question_docs = {
            str(qid1): {
                "_id": qid1,
                "stem": "Q1",
                "choices": [{"id": "a", "label": "Correct"}, {"id": "b", "label": "Wrong"}],
                "correct_choice_id": "a",
            },
            str(qid2): {
                "_id": qid2,
                "stem": "Q2",
                "choices": [{"id": "a", "label": "Right"}, {"id": "b", "label": "Picked"}],
                "correct_choice_id": "a",
            },
        }

        def find_one_side_effect(query, *args, **kwargs):
            if "_id" in query:
                qid = str(query["_id"])
                return question_docs.get(qid)
            return attempt_doc

        mock_col.find_one.side_effect = find_one_side_effect

        result = get_quiz_results(mock_db, "u1", "base")

        assert result.quiz_id == "base"
        assert result.total_questions == 2
        assert result.correct_count == 1
        assert len(result.items) == 2

        item1 = result.items[0]
        assert item1.question_number == 1
        assert item1.question_id == str(qid1)
        assert item1.is_correct is True
        assert item1.user_choice_label == "Correct"
        assert item1.correct_choice_label == "Correct"

        item2 = result.items[1]
        assert item2.question_number == 2
        assert item2.is_correct is False
        assert item2.user_choice_label == "Picked"
        assert item2.correct_choice_label == "Right"

    def test_skips_unanswered_questions(self, mock_db, mock_col):
        qid1 = ObjectId()
        qid2 = ObjectId()
        now = datetime.utcnow()

        attempt_doc = {
            "_id": ObjectId(),
            "question_order": [str(qid1), str(qid2)],
            "answers": [
                {"question_id": str(qid1), "answered_at": now, "choice_id": "a", "marked_correct": True},
                # qid2 was shown but not yet answered
                {"question_id": str(qid2), "answered_at": None, "choice_id": None},
            ],
        }

        question_doc1 = {
            "_id": qid1,
            "stem": "Q1",
            "choices": [{"id": "a", "label": "Correct"}],
            "correct_choice_id": "a",
        }

        def find_one_side_effect(query, *args, **kwargs):
            if "_id" in query:
                return question_doc1 if str(query["_id"]) == str(qid1) else None
            return attempt_doc

        mock_col.find_one.side_effect = find_one_side_effect

        result = get_quiz_results(mock_db, "u1", "base")

        assert result.total_questions == 1
        assert result.correct_count == 1
        assert result.items[0].question_id == str(qid1)

    def test_skips_deleted_questions(self, mock_db, mock_col):
        qid1 = ObjectId()
        now = datetime.utcnow()

        attempt_doc = {
            "_id": ObjectId(),
            "question_order": [str(qid1)],
            "answers": [
                {"question_id": str(qid1), "answered_at": now, "choice_id": "a", "marked_correct": True},
            ],
        }

        def find_one_side_effect(query, *args, **kwargs):
            if "_id" in query:
                return None  # question was deleted
            return attempt_doc

        mock_col.find_one.side_effect = find_one_side_effect

        result = get_quiz_results(mock_db, "u1", "base")

        assert result.total_questions == 0
        assert result.correct_count == 0
        assert result.items == []

    def test_empty_question_order_returns_empty_results(self, mock_db, mock_col):
        attempt_doc = {
            "_id": ObjectId(),
            "question_order": [],
            "answers": [],
        }
        mock_col.find_one.return_value = attempt_doc

        result = get_quiz_results(mock_db, "u1", "base")

        assert result.total_questions == 0
        assert result.correct_count == 0
        assert result.items == []
