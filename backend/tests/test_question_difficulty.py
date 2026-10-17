# backend/tests/test_question_difficulty.py
"""Unit tests for app/services/question_difficulty.py."""
from unittest.mock import MagicMock
from bson import ObjectId

from app.services.question_difficulty import llm_judge_difficulty, run_difficulty_judging


def _openai_returning(content):
    """Build a mock OpenAI client whose chat completion returns `content`."""
    client = MagicMock()
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    client.chat.completions.create.return_value = resp
    return client


class TestLlmJudgeDifficulty:
    def test_parses_easy(self):
        client = _openai_returning("EASY")
        assert llm_judge_difficulty("Stats", "Q?", [{"id": "a", "label": "1"}], client) == "easy"

    def test_parses_medium_case_insensitive_with_punctuation(self):
        client = _openai_returning("Medium.")
        assert llm_judge_difficulty("Stats", "Q?", [], client) == "medium"

    def test_parses_hard(self):
        client = _openai_returning("hard")
        assert llm_judge_difficulty("Stats", None, [], client) == "hard"

    def test_unrecognized_reply_returns_none(self):
        client = _openai_returning("I am not sure")
        assert llm_judge_difficulty("Stats", "Q?", [], client) is None

    def test_none_content_returns_none(self):
        client = _openai_returning(None)
        assert llm_judge_difficulty("Stats", "Q?", [], client) is None

    def test_fails_open_on_exception(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("upstream down")
        assert llm_judge_difficulty("Stats", "Q?", [], client) is None


class TestRunDifficultyJudging:
    def test_judges_unjudged_questions(self, mock_db, mock_col):
        docs = [
            {"_id": ObjectId(), "stem": "Stats", "subtitle": "Q1", "choices": [{"id": "a", "label": "1"}]},
            {"_id": ObjectId(), "stem": "Perm", "subtitle": "Q2", "choices": []},
        ]
        mock_col.find.return_value.limit.return_value = docs
        client = _openai_returning("HARD")

        result = run_difficulty_judging(mock_db, client)

        assert result == {"judged": 2, "skipped": 0}
        assert mock_col.update_one.call_count == 2
        set_doc = mock_col.update_one.call_args[0][1]["$set"]
        assert set_doc == {"difficulty": "hard", "difficulty_source": "ai", "difficulty_checked": True}
        # Only unjudged questions are selected.
        assert mock_col.find.call_args[0][0] == {"difficulty_checked": {"$ne": True}}

    def test_skips_questions_the_ai_cannot_classify(self, mock_db, mock_col):
        docs = [{"_id": ObjectId(), "stem": "Stats", "subtitle": "Q1", "choices": []}]
        mock_col.find.return_value.limit.return_value = docs
        client = _openai_returning("unsure")

        result = run_difficulty_judging(mock_db, client)

        assert result == {"judged": 0, "skipped": 1}
        mock_col.update_one.assert_not_called()

    def test_no_unjudged_questions_is_a_noop(self, mock_db, mock_col):
        mock_col.find.return_value.limit.return_value = []
        client = _openai_returning("EASY")

        result = run_difficulty_judging(mock_db, client)

        assert result == {"judged": 0, "skipped": 0}
        mock_col.update_one.assert_not_called()
        client.chat.completions.create.assert_not_called()
