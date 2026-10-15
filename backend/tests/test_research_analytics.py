import io
import json
import zipfile
from datetime import datetime, timedelta
from bson import ObjectId
import mongomock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.auth import get_current_user
from app.api.research import router, ensure_research_indexes
from app.api.export import router as export_router
from app.schemas.user import UserPublic
from app.services.research_analytics import research_data, variant_summaries, prompt_intents
from app.services.quiz import _load_or_create_attempt, build_quiz_state_response, record_answer, reset_quiz_attempt


@pytest.fixture
def study():
    db = mongomock.MongoClient().db
    uid, qid = ObjectId(), ObjectId()
    now = datetime(2026, 1, 1, 12)
    db.users.insert_one({"_id": uid, "email": "private@test.edu", "is_admin": False, "study_flow_version": 3,
                         "step_order": ["quiz:base"], "variant_sequence": ["links", "double", "followup"]})
    aid = db.quiz_attempts.insert_one({"user_id": str(uid), "user_email": "private@test.edu", "quiz_id": "links",
        "conversation_id": "conv", "question_order": [str(qid)], "question_set": "a", "status": "completed",
        "question_snapshots": {str(qid): {"correct_choice_id": "a", "stem": "Question", "version": "v1"}},
        "answers": [{"question_id": str(qid), "choice_id": "b", "marked_correct": False,
                     "shown_at": now, "answered_at": now + timedelta(seconds=10),
                     "telemetry_submission": {"page_id": "page", "elapsed_ms": 10000}}],
        "incorrect_question_ids": [], "created_at": now}).inserted_id
    ensure_research_indexes(db)
    app = FastAPI()
    app.state.db = db
    app.include_router(router)
    app.include_router(export_router)
    user = UserPublic(id=str(uid), email="private@test.edu")
    app.dependency_overrides[get_current_user] = lambda: user
    return db, TestClient(app), user, str(qid), str(aid), now


def event(qid, event_type="question_visible", event_id="event1", sequence=0, elapsed=0, **data):
    return {"event_id": event_id, "event_type": event_type, "conversation_id": "conv", "question_id": qid,
            "page_id": "page", "sequence": sequence, "occurred_at": "2026-01-01T12:00:00Z", "elapsed_ms": elapsed, "data": data}


def test_events_are_owned_deduplicated_and_immutable(study):
    db, client, user, qid, aid, _ = study
    payload = event(qid)
    assert client.post("/research/events", json={"events": [payload]}).json() == {"accepted": 1, "duplicates": 0}
    payload["data"] = {"visible": False}
    assert client.post("/research/events", json={"events": [payload]}).json() == {"accepted": 0, "duplicates": 1}
    stored = db.research_events.find_one()
    assert stored["attempt_id"] == aid and stored["user_id"] == user.id
    assert stored["data"] == {} and stored["received_at"]
    payload["conversation_id"] = "someone-elses"
    assert client.post("/research/events", json={"events": [payload]}).status_code == 403
    assert db.research_events.count_documents({}) == 1


def test_whole_batch_validated_and_unbounded_payload_rejected(study):
    db, client, _, qid, _, _ = study
    invalid = event("foreign-question", event_id="bad")
    assert client.post("/research/events", json={"events": [event(qid), invalid]}).status_code == 422
    assert db.research_events.count_documents({}) == 0
    assert client.post("/research/events", json={"events": [event(qid, duration_ms=15001)]}).status_code == 422
    assert client.post("/research/events", json={"events": [event(qid, user_email="spoof")] }).status_code == 422


def test_late_delivery_to_archived_attempt(study):
    db, client, user, qid, _, _ = study
    attempt = db.quiz_attempts.find_one()
    db.quiz_attempt_archive.insert_one(attempt)
    db.quiz_attempts.delete_many({})
    assert client.post("/research/events", json={"events": [event(qid)]}).status_code == 200


def add_recommendation(study, choice="b", exposed=True):
    db, client, user, qid, _, now = study
    db.messages.insert_one({"user_id": user.id, "conversation_id": "conv", "question_id": qid,
        "request_id": "request", "role": "assistant", "content": ["Answer B"], "created_at": now + timedelta(seconds=2),
        "metadata": {"stated_choice_id": {"default": choice}, "answer_incorrectly": False}})
    if exposed:
        assert client.post("/research/events", json={"events": [event(qid, "ai_message_displayed", request_id="request", agent="default", elapsed=2000)]}).status_code == 200


@pytest.mark.parametrize("choice,exposed,expected", [("b", True, True), ("a", True, False), (None, True, None), ("b", False, None)])
def test_actual_advice_and_exposure_not_manipulation_flag(study, choice, exposed, expected):
    add_recommendation(study, choice, exposed)
    db = study[0]
    row = research_data(db)[0]
    assert row["planned_wrong_ai"] is False
    assert row["wrong_ai_exposed"] is expected
    assert row["matched_wrong_ai"] is (True if expected is True else None)


def test_after_submission_advice_not_counted_and_interval_is_clipped(study):
    db, client, _, qid, _, _ = study
    add_recommendation(study, exposed=False)
    events = [event(qid, "ai_message_displayed", sequence=0, elapsed=11000, request_id="request", agent="default"),
              event(qid, "activity_interval", event_id="interval", sequence=1, elapsed=12000,
                    duration_ms=5000, visible_ms=5000, focused_ms=5000, active_ms=5000, pointer_ms=5000, region="chat")]
    client.post("/research/events", json={"events": events})
    row = research_data(db)[0]
    assert row["wrong_ai_exposed"] is None
    assert row["pointer_chat_ms"] == 3000 and row["active_ms"] == 3000


def test_feature_opportunity_rates_and_missing_values(study):
    db, client, _, qid, _, _ = study
    events = [event(qid, "suggestion_displayed", event_id="a", sequence=0, item_id="s1"),
              event(qid, "suggestion_displayed", event_id="b", sequence=1, item_id="s2"),
              event(qid, "suggestion_clicked", event_id="c", sequence=2, item_id="s1"),
              event(qid, "suggestion_clicked", event_id="d", sequence=3, item_id="s1"),
              event(qid, "reference_clicked", event_id="e", sequence=4, item_id="missing")]
    client.post("/research/events", json={"events": events})
    row = research_data(db)[0]
    assert row["suggestion_click_rate"] == 0.5 and row["suggestion_clicks"] == 2
    assert row["reference_click_rate"] is None and row["reference_clicks_without_impression"] == 1
    assert row["active_ms"] is None
    assert variant_summaries([row])[0]["wrong_ai_agreement_rate"] is None


def test_legacy_rows_and_test_accounts(study):
    db, _, user, _, _, _ = study
    db.quiz_attempts.update_many({}, {"$unset": {"question_snapshots": ""}})
    row = research_data(db)[0]
    assert row["wrong_ai_exposed"] is None and "missing_snapshot" in row["quality_flags"]
    db.users.update_one({"_id": ObjectId(user.id)}, {"$set": {"is_admin": True}})
    assert research_data(db) == []
    assert len(research_data(db, include_tests=True)) == 1


def test_snapshot_export_is_admin_only_and_omits_direct_identity(study):
    db, client, user, qid, _, _ = study
    assert client.get("/export/research-bundle").status_code == 403
    client.app.dependency_overrides[get_current_user] = lambda: user.model_copy(update={"is_admin": True})
    response = client.get("/export/research-bundle")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["analysis_version"] == "1.0"
        assert manifest["record_counts"]["questions"] == 1
        assert b"private@test.edu" not in archive.read("quiz_attempts.json")
        assert qid in archive.read("questions.json").decode()


def test_question_content_and_grading_are_frozen_at_attempt_creation():
    db = mongomock.MongoClient().db
    uid, qid = ObjectId(), ObjectId()
    db.users.insert_one({"_id": uid})
    db.questions.insert_one({"_id": qid, "stem": "Original", "choices": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}], "correct_choice_id": "a"})
    attempt = _load_or_create_attempt(db, str(uid), "a@test.edu", "base")
    db.questions.update_one({"_id": qid}, {"$set": {"stem": "Edited", "correct_choice_id": "b"}})
    assert build_quiz_state_response(db, attempt).current_question.stem == "Original"
    result = record_answer(db, str(uid), "base", str(qid), "a")
    assert result["answers"][0]["marked_correct"] is True
    # Reset archives the original answer and question version.
    reset_quiz_attempt(db, str(uid), "base")
    assert db.quiz_attempt_archive.find_one()["question_snapshots"][str(qid)]["stem"] == "Original"
    assert db.quiz_attempts.count_documents({}) == 0


def test_prompt_labels_are_multilabel_and_keep_unclassified():
    assert set(prompt_intents("Why? Please double check; your answer is wrong. Give a source.")) >= {"explanation", "double_check", "challenge", "source_verification"}
    assert prompt_intents("hello") == ["unclassified"]


def test_all_completed_variants_contribute_to_user_accuracy():
    from app.services.analytics import get_user_quiz_accuracy
    db = mongomock.MongoClient().db
    for variant, correct in [("links", True), ("double", False), ("followup", True)]:
        db.quiz_attempts.insert_one({"user_id": "student", "quiz_id": variant, "status": "completed",
                                    "answers": [{"answered_at": datetime.utcnow(), "marked_correct": correct}]})
    result = get_user_quiz_accuracy(db, "student", "variant")
    assert result["total"] == 3 and result["accuracy"] == 2 / 3


def test_offline_snapshot_analysis_is_reproducible(study, tmp_path):
    from scripts.analyze_research import analyze
    db, client, user, _, _, _ = study
    client.app.dependency_overrides[get_current_user] = lambda: user.model_copy(update={"is_admin": True})
    bundle = tmp_path / "snapshot.zip"
    bundle.write_bytes(client.get("/export/research-bundle").content)
    first = analyze(bundle, tmp_path / "first", seed=8, repetitions=100)
    second = analyze(bundle, tmp_path / "second", seed=8, repetitions=100)
    assert first == second
    assert first["variants"]["links"]["questions_answered"] == 1
    assert (tmp_path / "first" / "questions.csv").exists()


def test_interrupted_stream_keeps_the_prompt_and_partial_reply(study):
    import asyncio
    from app.services.research_chat import begin_request, track_stream
    from app.schemas.chat import ChatRequest
    db, _, user, qid, _, _ = study
    request = ChatRequest(message="Please explain", conversation_id="conv", question_id=qid, request_id="r", trigger="manual")
    context = begin_request(db, user, request, "conv", "links", "system prompt")

    async def partial():
        yield 'data: {"type":"token","content":"Possibly B"}\n\n'

    async def consume():
        return [chunk async for chunk in track_stream(partial(), db, context)]

    asyncio.run(consume())
    ledger = db.ai_requests.find_one({"request_id": "r"})
    assert ledger["prompt"] == "Please explain"
    assert ledger["status"] == "interrupted"
    assert ledger["partial_visible_replies"] == {"default": "Possibly B"}
    assert ledger["first_token_at"]


def test_second_tab_time_is_clipped_at_the_submitted_decision(study):
    db, client, _, qid, _, _ = study
    submit = event(qid, "answer_submit_clicked", event_id="submit", sequence=0, elapsed=10000)
    submit["occurred_at"] = "2026-01-01T12:00:10Z"
    interval = event(qid, "activity_interval", event_id="other-tab", sequence=0, elapsed=12000,
                     duration_ms=5000, active_ms=5000, focused_ms=5000, visible_ms=5000, pointer_ms=5000, region="chat")
    interval.update(page_id="other-page", occurred_at="2026-01-01T12:00:12Z")
    client.post("/research/events", json={"events": [submit, interval]})
    row = research_data(db)[0]
    assert row["active_ms"] == 3000
    assert "multiple_pages" in row["quality_flags"]


def test_unknown_second_agent_does_not_become_correct_advice(study):
    db, client, user, qid, _, now = study
    db.messages.insert_one({"user_id": user.id, "conversation_id": "conv", "question_id": qid,
        "request_id": "agents", "role": "assistant", "created_at": now,
        "metadata": {"stated_choice_id": {"A": "a", "B": None}}})
    client.post("/research/events", json={"events": [
        event(qid, "ai_message_displayed", event_id="A", sequence=0, request_id="agents", agent="A"),
        event(qid, "ai_message_displayed", event_id="B", sequence=1, request_id="agents", agent="B")]})
    row = research_data(db)[0]
    assert row["wrong_ai_exposed"] is None
    assert row["ai_recommendations_unresolved"] == 1
