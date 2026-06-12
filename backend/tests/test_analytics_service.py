# backend/tests/test_analytics_service.py
"""Unit tests for the analytics service: question/user/quiz accuracy aggregation."""

from app.services.analytics import (
    get_question_accuracy,
    get_user_quiz_accuracy,
    get_quiz_accuracy,
    _VARIANT_QUIZ_IDS,
)


# ── _VARIANT_QUIZ_IDS ────────────────────────────────────────────────────────

def test_variant_quiz_ids_match_assigned_var_enum():
    assert set(_VARIANT_QUIZ_IDS) == {"followup", "double", "links"}


# ── get_question_accuracy ────────────────────────────────────────────────────

class TestGetQuestionAccuracy:
    def test_normal_data_computes_accuracy(self, mock_col, mock_db):
        mock_col.find.return_value = [
            {
                "quiz_id": "base",
                "answers": [
                    {"question_id": "q1", "answered_at": "2024-01-01T00:00:00Z", "marked_correct": True},
                    {"question_id": "q1", "answered_at": "2024-01-01T00:00:00Z", "marked_correct": False},
                ],
            },
            {
                "quiz_id": "base",
                "answers": [
                    {"question_id": "q1", "answered_at": "2024-01-02T00:00:00Z", "marked_correct": True},
                ],
            },
        ]

        result = get_question_accuracy(mock_db, "q1")

        assert result["question_id"] == "q1"
        assert result["quiz_id"] is None
        assert result["total"] == 3
        assert result["correct"] == 2
        assert result["accuracy"] == 2 / 3

    def test_filters_by_quiz_id_when_provided(self, mock_col, mock_db):
        mock_col.find.return_value = []

        result = get_question_accuracy(mock_db, "q1", quiz_id="followup")

        # Verify the query passed to find() includes the quiz_id filter
        called_query, called_projection = mock_col.find.call_args[0]
        assert called_query == {"answers.question_id": "q1", "quiz_id": "followup"}
        assert called_projection == {"answers": 1, "quiz_id": 1}

        assert result["quiz_id"] == "followup"
        assert result["total"] == 0
        assert result["correct"] == 0
        assert result["accuracy"] is None

    def test_no_quiz_id_query_does_not_include_quiz_id_key(self, mock_col, mock_db):
        mock_col.find.return_value = []

        get_question_accuracy(mock_db, "q1")

        called_query, _ = mock_col.find.call_args[0]
        assert "quiz_id" not in called_query

    def test_ignores_answers_for_other_questions(self, mock_col, mock_db):
        mock_col.find.return_value = [
            {
                "quiz_id": "base",
                "answers": [
                    {"question_id": "q1", "answered_at": "2024-01-01T00:00:00Z", "marked_correct": True},
                    {"question_id": "q2", "answered_at": "2024-01-01T00:00:00Z", "marked_correct": False},
                ],
            },
        ]

        result = get_question_accuracy(mock_db, "q1")

        assert result["total"] == 1
        assert result["correct"] == 1
        assert result["accuracy"] == 1.0

    def test_ignores_unanswered_entries(self, mock_col, mock_db):
        mock_col.find.return_value = [
            {
                "quiz_id": "base",
                "answers": [
                    {"question_id": "q1", "answered_at": None, "marked_correct": True},
                ],
            },
        ]

        result = get_question_accuracy(mock_db, "q1")

        assert result["total"] == 0
        assert result["correct"] == 0
        assert result["accuracy"] is None

    def test_empty_results_returns_none_accuracy(self, mock_col, mock_db):
        mock_col.find.return_value = []

        result = get_question_accuracy(mock_db, "q-missing")

        assert result["total"] == 0
        assert result["correct"] == 0
        assert result["accuracy"] is None

    def test_attempt_with_no_answers_key(self, mock_col, mock_db):
        # attempt.get("answers", []) handles missing "answers" key gracefully
        mock_col.find.return_value = [{"quiz_id": "base"}]

        result = get_question_accuracy(mock_db, "q1")

        assert result["total"] == 0
        assert result["accuracy"] is None


# ── get_user_quiz_accuracy ────────────────────────────────────────────────────

class TestGetUserQuizAccuracy:
    def test_base_quiz_type_uses_base_filter(self, mock_col, mock_db):
        mock_col.find_one.return_value = None

        get_user_quiz_accuracy(mock_db, "user-1", "base")

        called_query, called_projection = mock_col.find_one.call_args[0]
        assert called_query == {"user_id": "user-1", "quiz_id": "base", "status": "completed"}
        assert called_projection == {"answers": 1, "quiz_id": 1}

    def test_variant_quiz_type_uses_in_filter(self, mock_col, mock_db):
        mock_col.find_one.return_value = None

        get_user_quiz_accuracy(mock_db, "user-1", "variant")

        called_query, _ = mock_col.find_one.call_args[0]
        assert called_query["quiz_id"] == {"$in": _VARIANT_QUIZ_IDS}

    def test_no_attempt_found_returns_zeroed_result(self, mock_col, mock_db):
        mock_col.find_one.return_value = None

        result = get_user_quiz_accuracy(mock_db, "user-1", "base")

        assert result == {
            "user_id": "user-1",
            "quiz_type": "base",
            "quiz_id": None,
            "total": 0,
            "correct": 0,
            "accuracy": None,
        }

    def test_attempt_found_computes_accuracy(self, mock_col, mock_db):
        mock_col.find_one.return_value = {
            "quiz_id": "base",
            "answers": [
                {"answered_at": "2024-01-01T00:00:00Z", "marked_correct": True},
                {"answered_at": "2024-01-01T00:00:00Z", "marked_correct": True},
                {"answered_at": "2024-01-01T00:00:00Z", "marked_correct": False},
                {"answered_at": "2024-01-01T00:00:00Z", "marked_correct": False},
            ],
        }

        result = get_user_quiz_accuracy(mock_db, "user-1", "base")

        assert result["user_id"] == "user-1"
        assert result["quiz_type"] == "base"
        assert result["quiz_id"] == "base"
        assert result["total"] == 4
        assert result["correct"] == 2
        assert result["accuracy"] == 0.5

    def test_attempt_found_but_no_answered_entries(self, mock_col, mock_db):
        mock_col.find_one.return_value = {
            "quiz_id": "followup",
            "answers": [
                {"answered_at": None, "marked_correct": True},
            ],
        }

        result = get_user_quiz_accuracy(mock_db, "user-1", "variant")

        assert result["quiz_id"] == "followup"
        assert result["total"] == 0
        assert result["correct"] == 0
        assert result["accuracy"] is None

    def test_attempt_found_with_no_answers_key(self, mock_col, mock_db):
        mock_col.find_one.return_value = {"quiz_id": "double"}

        result = get_user_quiz_accuracy(mock_db, "user-1", "variant")

        assert result["total"] == 0
        assert result["accuracy"] is None
        assert result["quiz_id"] == "double"


# ── get_quiz_accuracy ──────────────────────────────────────────────────────────

class TestGetQuizAccuracy:
    def test_normal_data_computes_accuracy(self, mock_col, mock_db):
        mock_col.find.return_value = [
            {
                "answers": [
                    {"answered_at": "2024-01-01T00:00:00Z", "marked_correct": True},
                    {"answered_at": "2024-01-01T00:00:00Z", "marked_correct": False},
                ],
            },
            {
                "answers": [
                    {"answered_at": "2024-01-01T00:00:00Z", "marked_correct": True},
                ],
            },
        ]

        result = get_quiz_accuracy(mock_db, "base")

        assert result["quiz_id"] == "base"
        assert result["attempts"] == 2
        assert result["total_answers"] == 3
        assert result["correct"] == 2
        assert result["accuracy"] == 2 / 3

        called_query, called_projection = mock_col.find.call_args[0]
        assert called_query == {"quiz_id": "base", "status": "completed"}
        assert called_projection == {"answers": 1}

    def test_no_attempts_returns_none_accuracy(self, mock_col, mock_db):
        mock_col.find.return_value = []

        result = get_quiz_accuracy(mock_db, "links")

        assert result["quiz_id"] == "links"
        assert result["attempts"] == 0
        assert result["total_answers"] == 0
        assert result["correct"] == 0
        assert result["accuracy"] is None

    def test_attempts_with_no_answered_entries(self, mock_col, mock_db):
        mock_col.find.return_value = [
            {"answers": [{"answered_at": None, "marked_correct": True}]},
            {"answers": []},
        ]

        result = get_quiz_accuracy(mock_db, "double")

        assert result["attempts"] == 2
        assert result["total_answers"] == 0
        assert result["correct"] == 0
        assert result["accuracy"] is None

    def test_attempts_with_no_answers_key(self, mock_col, mock_db):
        mock_col.find.return_value = [{}, {}]

        result = get_quiz_accuracy(mock_db, "followup")

        assert result["attempts"] == 2
        assert result["total_answers"] == 0
        assert result["accuracy"] is None
