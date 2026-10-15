# backend/tests/test_question_difficulty.py
"""Unit tests for app/services/question_difficulty.py."""
from unittest.mock import MagicMock
from bson import ObjectId

from app.core.llm import DEFAULT_MODEL
from app.services.question_difficulty import llm_judge_difficulty, run_difficulty_judging


def _openai_returning(content, served_model=None):
    """Build a mock OpenAI client whose chat completion returns `content`.

    `served_model` sets the `model` field the fake gateway echoes back; left
    unset it stays a MagicMock attribute, which the logger ignores.
    """
    client = MagicMock()
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    if served_model is not None:
        resp.model = served_model
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


# ── model resolution and served-model logging ─────────────────────────────────

class TestDifficultyServedModel:
    def test_requests_the_configured_model(self, monkeypatch):
        monkeypatch.setenv("UF_OPENAI_API_MODEL", "gpt-4.1")
        client = _openai_returning("EASY")

        llm_judge_difficulty("Stats", "Q?", [], client)

        assert client.chat.completions.create.call_args.kwargs["model"] == "gpt-4.1"

    def test_falls_back_to_the_shared_default(self, monkeypatch):
        monkeypatch.delenv("UF_OPENAI_API_MODEL", raising=False)
        client = _openai_returning("EASY")

        llm_judge_difficulty("Stats", "Q?", [], client)

        assert client.chat.completions.create.call_args.kwargs["model"] == DEFAULT_MODEL

    def test_logs_the_served_model(self, monkeypatch, capsys):
        monkeypatch.setenv("UF_OPENAI_API_MODEL", "gpt-4.1")
        client = _openai_returning("EASY", served_model="gpt-4.1")

        llm_judge_difficulty("Stats", "Q?", [], client)

        assert "[llm] question_difficulty: gateway served 'gpt-4.1'" in capsys.readouterr().out

    def test_warns_when_the_gateway_substitutes(self, monkeypatch, capsys):
        monkeypatch.setenv("UF_OPENAI_API_MODEL", "gpt-4.1")
        client = _openai_returning("EASY", served_model="gpt-4o-mini")

        llm_judge_difficulty("Stats", "Q?", [], client)

        out = capsys.readouterr().out
        assert "requested 'gpt-4.1'" in out
        assert "remapped" in out

    def test_failure_path_logs_nothing(self, capsys):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("upstream down")

        assert llm_judge_difficulty("Stats", "Q?", [], client) is None
        assert "[llm]" not in capsys.readouterr().out
