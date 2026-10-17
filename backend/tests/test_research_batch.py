import asyncio
import json
import zipfile
from unittest.mock import AsyncMock
import pytest
from tests.test_research_coding import case
from app.schemas.research_coding import ConversationCoding
from app.services.research_analytics import research_data, variant_summaries
from scripts.code_research import code_snapshot
from scripts.analyze_research import analyze


def snapshot(case, tmp_path):
    db, _, _, packet, _ = case
    rows = research_data(db)
    files = {"manifest": {"analysis_version": "1.2"}, "conversation_packets": [packet], "research_annotations": [],
        "questions": rows, "variants": variant_summaries(rows), "participants": [{"participant_id": packet["participant_id"]}]}
    path = tmp_path / "snapshot.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in files.items(): archive.writestr(name + ".json", json.dumps(value))
    return path


def test_default_batch_prepares_blinded_review_templates_and_resumes_without_model_calls(case, tmp_path, monkeypatch):
    provider = AsyncMock()
    monkeypatch.setattr("scripts.code_research.generate_coding", provider)
    path = snapshot(case, tmp_path)
    output = tmp_path / "reviews.jsonl"
    assert asyncio.run(code_snapshot(path, output))["written"] == 1
    template = json.loads(output.read_text())
    assert template["source"] == "human_template"
    assert "answer" not in template["blinded_packet"] and "quiz_id" not in template["blinded_packet"]
    assert asyncio.run(code_snapshot(path, output))["written"] == 0
    provider.assert_not_awaited()


def test_completed_offline_human_reviews_merge_into_metrics_with_evidence_validation(case, tmp_path):
    path = snapshot(case, tmp_path)
    output = tmp_path / "reviews.jsonl"
    asyncio.run(code_snapshot(path, output))
    template = json.loads(output.read_text())
    template.update(source="human", reviewer_id="researcher-1", independent_review=True, **case[4])
    output.write_text(json.dumps(template) + "\n")
    report = analyze(path, tmp_path / "analysis", repetitions=100, coding_results=[output])
    assert report["conversation_metrics"][0]["metrics"]["human_coded_reasoning"]["value"] == 1
    template["evidence"][0]["quote"] = "fabricated quote"
    output.write_text(json.dumps(template) + "\n")
    with pytest.raises(Exception): analyze(path, tmp_path / "bad", repetitions=100, coding_results=[output])


def test_explicit_model_batch_is_bounded_and_cached(case, tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_EVALUATOR_MODEL", "test-model")
    monkeypatch.setenv("UF_OPENAI_API_KEY", "test-not-real")
    provider = AsyncMock(return_value=(ConversationCoding(**case[4]), "test-model", {"provisional": True}))
    monkeypatch.setattr("scripts.code_research.generate_coding", provider)
    path = snapshot(case, tmp_path)
    output = tmp_path / "models.jsonl"
    assert asyncio.run(code_snapshot(path, output, method="llm", limit=1))["written"] == 1
    assert asyncio.run(code_snapshot(path, output, method="llm", limit=1))["written"] == 0
    assert provider.await_count == 1
    report = analyze(path, tmp_path / "analysis", repetitions=100, coding_results=[output])
    assert report["conversation_metrics"][0]["metrics"]["llm_coded_reasoning"]["value"] == 1
    assert report["conversation_metrics"][0]["metrics"]["human_coded_reasoning"]["value"] is None
