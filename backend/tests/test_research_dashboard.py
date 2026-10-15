import json
from datetime import datetime, timedelta
from bson import ObjectId
import mongomock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.auth import get_current_user
from app.api.research import router
from app.schemas.user import UserPublic
from app.services.research_dashboard import aggregate, filter_users, MISSING
from app.services.research_analytics import research_data


@pytest.fixture
def dashboard_study():
    db = mongomock.MongoClient().db
    now = datetime(2026, 1, 1)
    people = {}
    for name, demographics, extra in [
        ("Alice", {"gender": "Female", "academic_level": "Undergraduate", "year": "first", "age": "19", "major": "Data Science", "race_ethnicity": ["Asian", "White"], "class_name": "STA 2023"}, {}),
        ("Bob", {"gender": "Male", "academic_level": "Masters", "year": "second", "age": "25", "race_ethnicity": ["White"]}, {}),
        ("Carol", {}, {}), ("Test", {"gender": "Female"}, {"is_test": True}),
        ("Admin", {"gender": "Male"}, {"is_admin": True}),
    ]:
        uid = ObjectId()
        db.users.insert_one({"_id": uid, "first_name": name, "last_name": "Student", "email": f"{name.lower()}@test.edu",
                             "demographics": demographics, "study_flow_version": 2, "step_order": ["quiz:base"], "completed_steps": [], **extra})
        people[name] = str(uid)
    attempts = {}
    for name, count, correct in [("Alice", 5, True), ("Bob", 1, False), ("Test", 1, True), ("Admin", 1, True)]:
        qids = [str(ObjectId()) for _ in range(count)]
        attempt = {"user_id": people[name], "quiz_id": "base", "conversation_id": f"conv-{name}", "status": "completed",
                   "question_order": qids, "question_set": "a", "variant_position": 1, "study_flow_version": 2,
                   "question_snapshots": {qid: {"stem": "Frozen question", "correct_choice_id": "a", "version": "v1"} for qid in qids},
                   "answers": [{"question_id": qid, "choice_id": "a" if correct else "b", "marked_correct": correct,
                                "shown_at": now, "answered_at": now + timedelta(seconds=10)} for qid in qids], "created_at": now}
        attempts[name] = str(db.quiz_attempts.insert_one(attempt).inserted_id)
    app = FastAPI()
    app.state.db = db
    app.include_router(router)
    admin = UserPublic(id=people["Admin"], email="admin@test.edu", is_admin=True)
    app.dependency_overrides[get_current_user] = lambda: admin
    return db, TestClient(app), people, attempts


def test_equal_participant_weighting_and_complete_cohort_pagination(dashboard_study):
    db, client, people, _ = dashboard_study
    first = client.get("/research/results", params={"page_size": 1}).json()
    second = client.get("/research/results", params={"page_size": 1, "page": 2}).json()
    score = first["overall"]["metrics"]["accuracy"]
    assert score["value"] == .5  # Alice 100%, Bob 0%; not 5/6.
    assert score["pooled_value"] == 5 / 6
    assert score["participant_count"] == 2 and score["observation_count"] == 6
    assert first["matched_accounts"] == 3 and first["total_pages"] == 3
    assert first["overall"] == second["overall"]
    assert first["participants"][0]["participant_id"] != second["participants"][0]["participant_id"]
    assert "password_hash" not in json.dumps(first)


def test_demographic_filters_combine_and_match_multiselect_membership(dashboard_study):
    _, client, people, _ = dashboard_study
    result = client.get("/research/results", params={"filters": json.dumps({"gender": "female", "year": "first", "race_ethnicity": "White"}), "age_min": 18, "age_max": 20}).json()
    assert result["matched_accounts"] == 1
    assert result["participants"][0]["participant_id"] == people["Alice"]
    assert result["overall"]["metrics"]["accuracy"]["value"] == 1
    missing = client.get("/research/results", params={"filters": json.dumps({"academic_level": MISSING})}).json()
    assert missing["participants"][0]["participant_id"] == people["Carol"]
    assert missing["overall"]["metrics"]["accuracy"]["value"] is None


@pytest.mark.parametrize("query", ["ALICE", "alice@test.edu", "Alice Student"])
def test_search_names_and_emails_changes_averages(dashboard_study, query):
    _, client, _, _ = dashboard_study
    data = client.get("/research/results", params={"search": query}).json()
    assert data["matched_accounts"] == 1 and data["overall"]["metrics"]["accuracy"]["value"] == 1


def test_search_id_and_unstarted_account(dashboard_study):
    _, client, people, _ = dashboard_study
    data = client.get("/research/results", params={"search": people["Carol"]}).json()
    assert data["matched_accounts"] == 1 and data["overall"]["participant_count"] == 0
    assert data["participants"][0]["attempt_count"] == 0


def test_missing_measurements_are_excluded_but_zero_is_retained(dashboard_study):
    db, client, people, _ = dashboard_study
    attempt = db.quiz_attempts.find_one({"user_id": people["Bob"]})
    db.research_events.insert_one({"user_id": people["Bob"], "conversation_id": attempt["conversation_id"], "question_id": attempt["question_order"][0],
        "event_type": "activity_interval", "page_id": "p", "sequence": 0, "elapsed_ms": 1000,
        "data": {"duration_ms": 1000, "active_ms": 0, "visible_ms": 0, "focused_ms": 0, "pointer_ms": 0, "region": "chat"}})
    metrics = client.get("/research/results").json()["overall"]["metrics"]
    assert metrics["active_ms"]["value"] == 0 and metrics["active_ms"]["participant_count"] == 1
    assert metrics["pointer_chat_share"]["value"] is None
    assert metrics["wrong_ai_agreement"]["value"] is None


def test_opportunity_rates_are_averaged_per_participant():
    def row(pid, displayed, clicked):
        return {"participant_id": pid, "was_shown": True, "answered": True, "ai_requests": 1, "telemetry_available": True,
                "suggestions_displayed": displayed, "suggestions_clicked": clicked}
    metric = aggregate([row("a", 10, 10), row("b", 1, 0)])["metrics"]["suggestion_click_rate"]
    assert metric["value"] == .5 and metric["pooled_value"] == 10 / 11
    assert metric["denominator"] == 11 and metric["observation_count"] == 2


def test_status_version_set_and_test_filters(dashboard_study):
    db, client, people, _ = dashboard_study
    alice = db.quiz_attempts.find_one({"user_id": people["Alice"]})
    archived = {**alice, "_id": ObjectId(), "archived_at": datetime.utcnow(), "conversation_id": "archive", "quiz_id": "double"}
    db.quiz_attempt_archive.insert_one(archived)
    db.quiz_attempts.update_one({"_id": alice["_id"]}, {"$set": {"status": "in_progress"}})
    assert client.get("/research/results").json()["overall"]["participant_count"] == 1
    assert client.get("/research/results", params={"status": "all"}).json()["overall"]["participant_count"] == 2
    assert client.get("/research/results", params={"version": 99}).json()["overall"]["participant_count"] == 0
    assert client.get("/research/results", params={"question_set": "b"}).json()["overall"]["participant_count"] == 0
    assert client.get("/research/results", params={"include_tests": True}).json()["matched_accounts"] == 5
    with_archives = client.get("/research/results", params={"include_archived": True, "quiz_id": "double"}).json()
    assert with_archives["overall"]["questions_answered"] == 5


@pytest.mark.parametrize("params", [{"filters": "not-json"}, {"filters": "[]"}, {"filters": '{"password_hash":"x"}'}, {"filters": '{"gender":[]}'}, {"age_min": 40, "age_max": 20}, {"page": 0}, {"page_size": 501}, {"status": "bogus"}])
def test_invalid_queries_are_rejected(dashboard_study, params):
    assert dashboard_study[1].get("/research/results", params=params).status_code == 422


def test_results_and_details_require_admin_and_question_ownership(dashboard_study):
    db, client, people, attempts = dashboard_study
    alice = db.quiz_attempts.find_one({"user_id": people["Alice"]})
    path = f'/research/participants/{people["Alice"]}/questions/{attempts["Alice"]}/{alice["question_order"][0]}'
    assert client.get(path).status_code == 200
    wrong = path.replace(people["Alice"], people["Bob"])
    assert client.get(wrong).status_code == 404
    assert client.get("/research/participants/invalid").status_code == 404
    assert client.get(f'/research/participants/{people["Admin"]}').status_code == 404
    client.app.dependency_overrides[get_current_user] = lambda: UserPublic(id=people["Bob"], email="bob@test.edu")
    for url in ("/research/results", f'/research/participants/{people["Alice"]}', path):
        assert client.get(url).status_code == 403
    client.app.dependency_overrides.clear()
    assert client.get("/research/results").status_code == 401


def test_individual_detail_and_interaction_pagination(dashboard_study):
    db, client, people, attempts = dashboard_study
    attempt = db.quiz_attempts.find_one({"user_id": people["Alice"]})
    qid = attempt["question_order"][0]
    query = {"user_id": people["Alice"], "conversation_id": attempt["conversation_id"], "question_id": qid}
    db.messages.insert_one({**query, "role": "user", "content": "Please double check", "trigger": "manual", "created_at": datetime.utcnow()})
    db.copy_events.insert_one({**query, "copied_text": "Selected explanation", "created_at": datetime.utcnow()})
    for index in range(3):
        db.research_events.insert_one({**query, "event_id": str(index), "event_type": "question_visible", "sequence": index, "page_id": "p", "elapsed_ms": index, "occurred_at": datetime.utcnow()})
    person = client.get(f'/research/participants/{people["Alice"]}').json()
    assert person["participant"]["email"] == "alice@test.edu" and len(person["questions"]) == 5
    trace = client.get(f'/research/participants/{people["Alice"]}/questions/{attempts["Alice"]}/{qid}', params={"event_page_size": 2, "event_page": 2}).json()
    assert trace["messages"][0]["intent_labels_heuristic"] == ["double_check"]
    assert trace["events_total"] == 3 and len(trace["events"]) == 1
    assert trace["copies"][0]["text"] == "Selected explanation"


def test_nan_age_does_not_pass_range_filters():
    assert filter_users([{"_id": ObjectId(), "demographics": {"age": "nan"}}], {}, age_min=18) == []


def test_statistics_share_cohort_filters_and_are_admin_only(dashboard_study):
    db, client, people, _ = dashboard_study
    assert client.get("/research/statistics", params={"search": "not-a-user"}).json()["paired"]["comparisons"] == []
    assert client.get("/research/statistics", params={"filters": '{"password_hash":"x"}'}).status_code == 422
    assert client.get("/research/statistics", params={"age_min": 40, "age_max": 20}).status_code == 422
    client.app.dependency_overrides[get_current_user] = lambda: UserPublic(id=people["Bob"], email="bob@test.edu")
    assert client.get("/research/statistics").status_code == 403


def test_four_completed_records_can_have_eleven_answers_but_only_ten_grades(dashboard_study):
    db, client, people, _ = dashboard_study
    db.quiz_attempts.delete_many({})
    now = datetime(2026, 1, 1)
    for quiz, assigned, answered, correct, frozen in [
        ("base", 7, 0, 0, False), ("links", 7, 1, 0, False),
        ("followup", 5, 5, 2, True), ("double", 5, 5, 1, True),
    ]:
        qids = [str(ObjectId()) for _ in range(assigned)]
        answers = [{"question_id": qid, "choice_id": "a", "shown_at": now, "answered_at": now,
                    **({"marked_correct": index < correct} if frozen else {})}
                   for index, qid in enumerate(qids[:answered])]
        if not answered:
            answers = [{"question_id": qids[0], "shown_at": now, "answered_at": None}]
        db.quiz_attempts.insert_one({"user_id": people["Alice"], "quiz_id": quiz, "status": "completed",
            "conversation_id": quiz, "question_order": qids, "answers": answers,
            "question_snapshots": {qid: {"correct_choice_id": "a"} for qid in qids} if frozen else {}})
        if frozen:
            for qid in qids:
                db.research_events.insert_one({"user_id": people["Alice"], "conversation_id": quiz, "question_id": qid,
                    "event_type": "activity_interval", "page_id": qid, "sequence": 0, "elapsed_ms": 9000,
                    "data": {"duration_ms": 9000, "active_ms": 9000}})
    data = client.get("/research/results", params={"search": people["Alice"]}).json()
    overall = data["overall"]
    assert overall["participant_count"] == 1 and overall["attempt_count"] == 4
    assert overall["completed_attempt_count"] == 4 and overall["incomplete_completed_attempt_count"] == 2
    assert overall["questions_assigned"] == 24 and overall["questions_shown"] == 12
    assert overall["questions_answered"] == 11 and overall["questions_graded"] == 10
    assert overall["answers_missing_grade"] == 1
    assert overall["metrics"]["accuracy"]["value"] == .3
    assert overall["metrics"]["accuracy"]["denominator"] == 10
    assert overall["metrics"]["telemetry_coverage"]["denominator"] == 12
    assert overall["metrics"]["telemetry_coverage"]["value"] == 10 / 12
    assert overall["metrics"]["active_ms"]["value"] == 9000
    variants = {v["quiz_id"]: v for v in data["variants"]}
    assert variants["base"]["attempt_count"] == 1 and variants["base"]["questions_answered"] == 0
    assert variants["links"]["questions_graded"] == 0 and variants["links"]["metrics"]["accuracy"]["value"] is None
    assert variants["followup"]["metrics"]["accuracy"]["value"] == .4
    assert variants["double"]["metrics"]["accuracy"]["value"] == .2
    detail = client.get(f'/research/participants/{people["Alice"]}').json()
    assert detail["overall"] == overall
    selected = client.get("/research/results", params={"search": people["Alice"], "quiz_id": "followup"}).json()["overall"]
    assert selected["attempt_count"] == 1 and selected["questions_graded"] == 5


def test_empty_completed_attempt_is_counted_without_fabricating_question_rows(dashboard_study):
    db, client, people, _ = dashboard_study
    db.quiz_attempts.delete_many({})
    db.quiz_attempts.insert_one({"user_id": people["Alice"], "quiz_id": "base", "status": "completed", "question_order": [], "answers": []})
    data = client.get("/research/results", params={"search": people["Alice"]}).json()
    overall = data["overall"]
    assert overall["attempt_count"] == 1 and overall["participant_count"] == 1
    assert overall["incomplete_completed_attempt_count"] == 1
    assert overall["questions_answered"] == 0 and overall["metrics"]["accuracy"]["value"] is None
    assert data["participants"][0]["attempt_count"] == 1
    assert data["variants"][0]["quiz_id"] == "base"
    assert client.get(f'/research/participants/{people["Alice"]}').json()["overall"] == overall


def test_inspect_returns_the_frozen_question_and_answer_after_bank_changes(dashboard_study):
    db, client, people, _ = dashboard_study
    attempt = db.quiz_attempts.find_one({"user_id": people["Alice"]})
    qid = attempt["question_order"][0]
    frozen = {"stem": "Original math question", "subtitle": "Find $x$.", "correct_choice_id": "a",
              "choices": [{"id": "a", "label": "Original correct option"}, {"id": "b", "label": "Original wrong option"}]}
    db.quiz_attempts.update_one({"_id": attempt["_id"]}, {"$set": {
        f"question_snapshots.{qid}": frozen, "answers.0.choice_id": "b", "answers.0.marked_correct": False,
    }})
    db.questions.insert_one({"_id": ObjectId(qid), "stem": "Replaced question", "correct_choice_id": "b"})
    path = f'/research/participants/{people["Alice"]}/questions/{attempt["_id"]}/{qid}'
    trace = client.get(path)
    assert trace.status_code == 200, trace.text
    assert trace.json()["snapshot"] == frozen
    assert trace.json()["snapshot_source"] == "attempt"
    assert trace.json()["answer"]["choice_id"] == "b"
    assert trace.json()["answer"]["correct_choice_id"] == "a"
    assert trace.json()["answer"]["correct"] is False
    db.questions.delete_many({})
    assert client.get(path).json()["snapshot"] == frozen


def test_legacy_inspect_without_conversation_or_snapshot_reports_unavailable(dashboard_study):
    db, client, people, _ = dashboard_study
    attempt = db.quiz_attempts.find_one({"user_id": people["Alice"]})
    qid = attempt["question_order"][0]
    db.quiz_attempts.update_one({"_id": attempt["_id"]}, {"$unset": {"conversation_id": "", "question_snapshots": "", "answers.0.marked_correct": ""}})
    db.messages.insert_one({"user_id": people["Alice"], "question_id": qid, "role": "assistant", "content": "Unrelated attempt"})
    path = f'/research/participants/{people["Alice"]}/questions/{attempt["_id"]}/{qid}'
    trace = client.get(path)
    assert trace.status_code == 200, trace.text
    assert trace.json()["snapshot"] is None and trace.json()["snapshot_source"] == "unavailable"
    assert trace.json()["answer"]["correct"] is None
    assert trace.json()["messages"] == []


def test_inspect_archived_question_uses_its_original_attempt(dashboard_study):
    db, client, people, _ = dashboard_study
    attempt = db.quiz_attempts.find_one({"user_id": people["Alice"]})
    qid = attempt["question_order"][0]
    db.quiz_attempt_archive.insert_one({**attempt, "archived_at": datetime.utcnow()})
    db.quiz_attempts.delete_one({"_id": attempt["_id"]})
    db.quiz_attempts.insert_one({**attempt, "_id": ObjectId(), "conversation_id": "new-run",
        "question_snapshots": {qid: {"stem": "Different run", "correct_choice_id": "b"}}})
    path = f'/research/participants/{people["Alice"]}/questions/{attempt["_id"]}/{qid}'
    assert client.get(path).status_code == 404
    trace = client.get(path, params={"include_archived": True})
    assert trace.status_code == 200, trace.text
    assert trace.json()["snapshot"]["stem"] == "Frozen question"
