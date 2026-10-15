import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import mongomock
import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.research import router
from app.api.auth import get_current_user
from app.schemas.user import UserPublic
from app.schemas.research_coding import ConversationCoding
from app.services import research_coding as coding
from app.services.research_analytics import research_data


@pytest.fixture
def case():
    db = mongomock.MongoClient().db
    uid, aid, qid = ObjectId(), ObjectId(), str(ObjectId())
    now = datetime(2026, 1, 1)
    db.users.insert_one({"_id": uid, "email": "student@test.edu"})
    db.quiz_attempts.insert_one({"_id": aid, "user_id": str(uid), "quiz_id": "base", "conversation_id": "conv", "status": "completed",
        "question_order": [qid], "question_snapshots": {qid: {"stem": "2+2?", "correct_choice_id": "a"}},
        "answers": [{"question_id": qid, "choice_id": "a", "marked_correct": True, "answered_at": now + timedelta(seconds=10)}]})
    db.messages.insert_many([{"user_id": str(uid), "conversation_id": "conv", "question_id": qid, "role": "user",
        "content": "I calculated 2+2=4", "trigger": "manual", "created_at": now},
        {"user_id": str(uid), "conversation_id": "conv", "question_id": qid, "role": "assistant", "content": ["Yes, A"], "created_at": now + timedelta(seconds=1)}])
    app = FastAPI(); app.state.db = db; app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: UserPublic(id="reviewer1", email="admin@test.edu", is_admin=True)
    client = TestClient(app)
    path = f"/research/participants/{uid}/questions/{aid}/{qid}/coding"
    packet = client.get(path).json()["packet"]
    labels = {key: "not_observed" for key in coding.RUBRIC}
    labels.update(student_reasoning="specific_step", suggestion_quality="insufficient_evidence")
    evidence = [{"dimension": "student_reasoning", "turn_id": packet["turns"][0]["turn_id"], "quote": "2+2=4"}]
    return db, client, path, packet, {"labels": labels, "evidence": evidence, "notes": ""}


def test_review_is_owned_versioned_and_append_only(case):
    db, client, path, packet, result = case
    body = {**result, "packet_hash": packet["packet_hash"], "independent_review": True}
    assert client.post(path + "/review", json=body).status_code == 200
    assert client.post(path + "/review", json=body).status_code == 200
    assert db.research_annotations.count_documents({}) == 2
    assert client.get(path).json()["annotations"][0]["reviewer_id"] == "reviewer1"
    row = research_data(db)[0]
    assert row["human_coding_reviewers"] == 1 and row["human_coded_reasoning"] is True
    assert row["llm_coded_reasoning"] is None


@pytest.mark.parametrize("failure", ["quote", "role", "dimension", "missing_evidence", "stale_packet"])
def test_fabricated_or_stale_annotations_are_rejected(case, failure):
    db, client, path, packet, result = case
    body = {**result, "packet_hash": packet["packet_hash"]}
    if failure == "quote": body["evidence"][0]["quote"] = "I never wrote this"
    if failure == "role": body["evidence"][0].update(turn_id=packet["turns"][1]["turn_id"], quote="Yes")
    if failure == "dimension": body["evidence"][0]["dimension"] = "invented_score"
    if failure == "missing_evidence": body["evidence"] = []
    if failure == "stale_packet": body["packet_hash"] = "0" * 64
    assert client.post(path + "/review", json=body).status_code == (409 if failure == "stale_packet" else 422)
    assert db.research_annotations.count_documents({}) == 0


def test_model_input_is_blinded_and_auto_prompts_are_identified(case):
    _, _, _, packet, _ = case
    payload = coding.model_input(packet)
    text = json.dumps(payload)
    assert "participant_id" not in text and "quiz_id" not in text and "answered_at" not in text
    assert "demographics" not in text and "marked_correct" not in text
    assert payload["question"]["correct_choice_id"] == "a"


def test_optional_evaluator_disabled_does_not_save_or_call(case, monkeypatch):
    db, client, path, packet, _ = case
    monkeypatch.delenv("RESEARCH_EVALUATOR_MODEL", raising=False)
    assert client.post(path + "/evaluate", json={"packet_hash": packet["packet_hash"]}).status_code == 503
    assert db.research_annotations.count_documents({}) == 0


def test_model_output_is_validated_cached_and_never_becomes_human_coding(case, monkeypatch):
    db, client, path, packet, result = case
    monkeypatch.setenv("UF_OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("RESEARCH_EVALUATOR_MODEL", "research-test")
    create = AsyncMock(return_value=SimpleNamespace(model="served-test", choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(result)))]))
    class Provider:
        def __init__(self, **kwargs): self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    monkeypatch.setattr("openai.AsyncOpenAI", Provider)
    for _ in range(2):
        response = client.post(path + "/evaluate", json={"packet_hash": packet["packet_hash"]})
        assert response.status_code == 200, response.text
    assert create.await_count == 1 and db.research_annotations.count_documents({}) == 1
    row = research_data(db)[0]
    assert row["llm_coded_reasoning"] is True and row["human_coded_reasoning"] is None
    sent = create.call_args.kwargs["messages"][1]["content"]
    assert "student@test.edu" not in sent and "participant_id" not in sent


def test_coding_and_validation_are_admin_only(case):
    _, client, path, packet, result = case
    client.app.dependency_overrides[get_current_user] = lambda: UserPublic(id="student", email="student@test.edu")
    assert client.get(path).status_code == 403
    assert client.post(path + "/review", json={**result, "packet_hash": packet["packet_hash"]}).status_code == 403
    assert client.get("/research/coding/validation").status_code == 403


def test_validation_requires_independent_reviewers_and_reports_class_support(case):
    _, _, _, packet, result = case
    def record(source, reviewer, label, independent=True, model=None):
        return {"_id": str(ObjectId()), "user_id": packet["participant_id"], "attempt_id": packet["attempt_id"], "question_id": packet["question_id"],
            "packet_hash": packet["packet_hash"], "rubric_version": coding.RUBRIC_VERSION, "partition": "validation", "source": source,
            "reviewer_id": reviewer, "model": model, "independent_review": independent, "created_at": datetime.now(timezone.utc),
            "labels": {**result["labels"], "student_reasoning": label}}
    one = record("human", "a", "specific_step")
    model = record("llm", None, "worked_reasoning", model="test")
    assert coding.validation_report([one, model])["model_validation"] == []
    two = record("human", "b", "specific_step")
    report = coding.validation_report([one, two, model])
    metric = next(r for r in report["model_validation"] if r["dimension"] == "student_reasoning")
    assert metric["n"] == 1 and metric["agreement"] == 0
    assert next(r for r in metric["classes"] if r["label"] == "specific_step")["recall"] == 0
    assert report["automatically_validated"] is False
    two["independent_review"] = False
    assert coding.validation_report([one, two, model])["model_validation"] == []


def test_participant_split_is_stable_and_conflicting_human_labels_are_unavailable(case):
    db, client, path, packet, result = case
    assert coding.validation_partition("person") == coding.validation_partition("person")
    client.post(path + "/review", json={**result, "packet_hash": packet["packet_hash"]})
    client.app.dependency_overrides[get_current_user] = lambda: UserPublic(id="reviewer2", email="other@test.edu", is_admin=True)
    result["labels"]["student_reasoning"] = "not_observed"
    assert client.post(path + "/review", json={**result, "packet_hash": packet["packet_hash"]}).status_code == 200
    row = research_data(db)[0]
    assert row["human_coding_conflict"] is True and row["human_coded_reasoning"] is None
