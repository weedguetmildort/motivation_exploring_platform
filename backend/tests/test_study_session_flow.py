"""Walk the real routes with session cookies and stateful Mongo semantics.

Unlike per-router tests, these do not override authentication or mock progress
updates. They exercise the actual signup, quiz, survey and next-step services.
No live database or AI calls are needed.
"""
from datetime import datetime, timedelta, timezone
from bson import ObjectId

import mongomock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from pymongo.errors import DuplicateKeyError

from app.api import auth, quiz, study, surveys
from app.core.config import get_settings
from app.services import study_flow as sf


@pytest.fixture
def session_app(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)
    monkeypatch.setattr(settings, "COOKIE_DOMAIN", None)
    db = mongomock.MongoClient().study_session_test
    for set_id in ("a", "b", "c", "d"):
        db.questions.insert_one({
            "stem": f"Question from set {set_id}", "set": set_id,
            "choices": [{"id": "a", "label": "Correct"}, {"id": "b", "label": "Other"}],
            "correct_choice_id": "a",
        })
    for stage in ("pre_quiz", "post_base"):
        db.survey_items.insert_one({
            "stage": stage, "prompt": "How motivated are you?", "type": "likert",
            "required": True, "active": True, "order": 0,
        })
    app = FastAPI()
    app.state.db = db
    for module in (auth, quiz, study, surveys):
        app.include_router(module.router)
    return app


def signup(client):
    response = client.post("/auth/signup", json={
        "email": "student@example.com", "password": "test-password",
        "first_name": "Test", "last_name": "Student", "consent": True,
    })
    assert response.status_code == 200, response.text
    return response.json()["user"]


def complete_current_step(client, step):
    if step["kind"] == "survey":
        prefix = f"/surveys/{step['key']}"
        state = client.get(f"{prefix}/state")
        assert state.status_code == 200, state.text
        response = client.post(f"{prefix}/submit", json={
            "answers": [{"item_id": item["id"], "value": 3} for item in state.json()["items"]],
        })
    else:
        prefix = f"/quiz/{step['key']}"
        state = client.get(f"{prefix}/state")
        assert state.status_code == 200, state.text
        response = client.post(f"{prefix}/answer", json={
            "question_id": state.json()["current_question"]["id"], "choice_id": "a",
        })
    assert response.status_code == 200, response.text
    assert response.json()["attempt"]["status"] == "completed"


@pytest.mark.parametrize("mode", sf.QUIZ_SET_MODES)
@pytest.mark.parametrize("rotation", [0, 1, 2])
def test_cookie_authenticated_participant_completes_all_nine_steps(session_app, mode, rotation):
    db = session_app.state.db
    sf.save_study_config(db, quiz_set_mode=mode, quiz_set_map={
        "base": "a", "followup": "b", "double": "c", "links": "d",
    })
    db.counters.insert_one({"_id": sf.ROUND_ROBIN_COUNTER_ID, "seq": rotation})
    client = TestClient(session_app)
    user = signup(client)
    assert len(user["step_order"]) == 9
    visited = []
    for expected_id in user["step_order"]:
        next_response = client.get("/study/next")
        assert next_response.status_code == 200, next_response.text
        step = next_response.json()["next_step"]
        assert step["id"] == expected_id
        complete_current_step(client, step)
        visited.append(step["id"])
        # A fresh /auth/me must expose the completed step on every transition.
        me = client.get("/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["user"]["completed_steps"] == visited
    assert client.get("/study/next").json()["finished"] is True
    assert db.quiz_attempts.count_documents({}) == 4
    assert db.survey_responses.count_documents({}) == 5


@pytest.mark.parametrize("completed_count", [1, 2])
@pytest.mark.parametrize("cookie_problem", ["missing", "expired", "wrong_secret"])
def test_session_failure_after_first_survey_or_quiz_can_resume(
    session_app, completed_count, cookie_problem
):
    client = TestClient(session_app)
    signup(client)
    for _ in range(completed_count):
        complete_current_step(client, client.get("/study/next").json()["next_step"])
    step_before = client.get("/study/next").json()["next_step"]
    client.cookies.clear()
    settings = get_settings()
    if cookie_problem != "missing":
        now = datetime.now(timezone.utc)
        expires = now - timedelta(minutes=1) if cookie_problem == "expired" else now + timedelta(hours=1)
        token = jwt.encode({"sub": "student@example.com", "exp": int(expires.timestamp())},
                           "other-deployment-secret" if cookie_problem == "wrong_secret" else settings.JWT_SECRET,
                           algorithm=settings.JWT_ALG)
        client.cookies.set(settings.COOKIE_NAME, token)
    prefix = f"/{'surveys' if step_before['kind'] == 'survey' else 'quiz'}/{step_before['key']}"
    assert client.get("/study/next").status_code == 401
    assert client.get(f"{prefix}/state").status_code == 401
    client.cookies.clear()
    assert client.post("/auth/login", json={"email": "student@example.com", "password": "test-password"}).status_code == 200
    assert client.get("/study/next").json()["next_step"] == step_before
    assert client.get(f"{prefix}/state").status_code == 200


@pytest.mark.parametrize("has_flow_snapshot", [False, True])
def test_old_account_restores_completed_results_even_when_flags_are_false(session_app, has_flow_snapshot):
    client = TestClient(session_app)
    user = signup(client)
    db = session_app.state.db
    uid = user["id"]
    original_assignment = user["quiz_set_assignment"]
    for _ in range(2):
        complete_current_step(client, client.get("/study/next").json()["next_step"])
    saved_survey = db.survey_responses.find_one({"user_id": uid, "stage": "pre_quiz"})
    unset = {"progress_reconciled_version": ""}
    if not has_flow_snapshot:
        unset.update(step_order="", completed_steps="")
    db.users.update_one({"_id": ObjectId(uid)}, {
        "$unset": unset,
        "$set": {"survey_pre_base_completed": False, "quiz_base_completed": False,
                 **({"completed_steps": []} if has_flow_snapshot else {})},
    })
    client.cookies.clear()
    login = client.post("/auth/login", json={"email": user["email"], "password": "test-password"})
    assert login.status_code == 200, login.text
    restored = login.json()["user"]
    assert restored["completed_steps"] == ["survey:pre_quiz", "quiz:base"]
    assert restored["quiz_set_assignment"] == original_assignment
    assert client.get("/study/next").json()["next_step"]["id"] == "survey:post_base"
    assert client.get("/auth/me").json()["user"]["completed_steps"] == restored["completed_steps"]
    assert db.survey_responses.find_one({"_id": saved_survey["_id"]}) == saved_survey


def test_legacy_post_variant_only_completes_the_assigned_variant_survey(session_app):
    client = TestClient(session_app)
    user = signup(client)
    db = session_app.state.db
    db.users.update_one({"_id": ObjectId(user["id"])}, {"$unset": {"progress_reconciled_version": ""}})
    db.survey_responses.insert_one({"user_id": user["id"], "stage": "post_variant", "status": "completed"})
    db.survey_responses.insert_one({"user_id": user["id"], "stage": "post_base", "status": "in_progress"})
    db.survey_responses.insert_one({"user_id": str(ObjectId()), "stage": "pre_quiz", "status": "completed"})
    db.quiz_attempt_archive.insert_one({"user_id": user["id"], "quiz_id": "base", "status": "completed"})
    me = client.get("/auth/me").json()["user"]
    assert me["completed_steps"] == [sf.survey_step_id(sf.post_variant_stage(user["assigned_var"]))]
    assert me["quiz_set_assignment"] == user["quiz_set_assignment"]
    assert client.get("/study/next").json()["next_step"]["id"] == "survey:pre_quiz"


def test_progress_repair_preserves_a_concurrent_completion(session_app, monkeypatch):
    client = TestClient(session_app)
    user = signup(client)
    db = session_app.state.db
    db.users.update_one({"_id": ObjectId(user["id"])}, {"$unset": {"progress_reconciled_version": ""}})
    db.survey_responses.insert_one({"user_id": user["id"], "stage": "pre_quiz", "status": "completed"})
    original_update = db.users.update_one
    raced = False

    def concurrent_update(query, update, *args, **kwargs):
        nonlocal raced
        if "progress_reconciled_version" in query and not raced:
            raced = True
            original_update({"_id": ObjectId(user["id"])}, {"$set": {"completed_steps": ["quiz:base"]}})
        return original_update(query, update, *args, **kwargs)

    monkeypatch.setattr(db.users, "update_one", concurrent_update)
    assert client.get("/auth/me").json()["user"]["completed_steps"] == ["survey:pre_quiz", "quiz:base"]


def test_completed_survey_retry_preserves_answers_and_blocks_future_surveys(session_app):
    client = TestClient(session_app)
    user = signup(client)
    complete_current_step(client, client.get("/study/next").json()["next_step"])
    db = session_app.state.db
    saved = db.survey_responses.find_one({"user_id": user["id"], "stage": "pre_quiz"})
    retry = client.post("/surveys/pre_quiz/submit", json={
        "answers": [{"item_id": saved["answers"][0]["item_id"], "value": 5}],
    })
    assert retry.status_code == 200, retry.text
    assert retry.json()["attempt"]["status"] == "completed"
    assert db.survey_responses.find_one({"_id": saved["_id"]}) == saved
    assert client.get("/surveys/pre_quiz/state").status_code == 200
    assert client.get("/study/next").json()["next_step"]["id"] == "quiz:base"
    assert client.get("/surveys/post_base/state").status_code == 403
    assert client.post("/surveys/post_base/submit", json={"answers": []}).status_code == 403


@pytest.mark.parametrize("recovery_request", ["state", "submit"])
def test_completed_survey_repairs_a_failed_progress_write_after_initial_migration(session_app, recovery_request):
    client = TestClient(session_app)
    user = signup(client)
    complete_current_step(client, client.get("/study/next").json()["next_step"])
    db = session_app.state.db
    saved = db.survey_responses.find_one({"user_id": user["id"]})
    # Simulate the response save succeeding but the separate user write failing.
    db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"completed_steps": []}})
    if recovery_request == "state":
        response = client.get("/surveys/pre_quiz/state")
    else:
        response = client.post("/surveys/pre_quiz/submit", json={"answers": []})
    assert response.status_code == 200, response.text
    assert client.get("/study/next").json()["next_step"]["id"] == "quiz:base"
    assert db.survey_responses.find_one({"_id": saved["_id"]}) == saved


def test_completed_quiz_accepts_identical_retry_without_changing_research_timing(session_app):
    client = TestClient(session_app)
    user = signup(client)
    for _ in range(2):
        complete_current_step(client, client.get("/study/next").json()["next_step"])
    db = session_app.state.db
    saved = db.quiz_attempts.find_one({"user_id": user["id"], "quiz_id": "base"})
    question_id = saved["answers"][0]["question_id"]
    # Also simulate a failed progress write for a completed quiz.
    db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"completed_steps": ["survey:pre_quiz"]}})
    for _ in range(2):
        response = client.post("/quiz/base/answer", json={"question_id": question_id, "choice_id": "a"})
        assert response.status_code == 200, response.text
        assert response.json()["attempt"]["status"] == "completed"
    assert client.get("/quiz/base/state").status_code == 200
    assert client.post("/quiz/base/answer", json={"question_id": question_id, "choice_id": "b"}).status_code == 400
    assert db.quiz_attempts.find_one({"_id": saved["_id"]}) == saved
    assert client.get("/study/next").json()["next_step"]["id"] == "survey:post_base"


def test_two_tabs_creating_the_same_survey_share_one_response(session_app, monkeypatch):
    client = TestClient(session_app)
    signup(client)
    col = session_app.state.db.survey_responses
    col.create_index([("user_id", 1), ("stage", 1)], unique=True)
    original_insert = col.insert_one

    def other_tab_inserts_first(doc):
        original_insert(dict(doc))
        raise DuplicateKeyError("other tab created this response")

    monkeypatch.setattr(col, "insert_one", other_tab_inserts_first)
    response = client.get("/surveys/pre_quiz/state")
    assert response.status_code == 200, response.text
    assert col.count_documents({}) == 1


def test_survey_completed_by_another_tab_cannot_be_overwritten(session_app, monkeypatch):
    client = TestClient(session_app)
    user = signup(client)
    state = client.get("/surveys/pre_quiz/state").json()
    db = session_app.state.db
    col = db.survey_responses
    original_update = col.update_one
    completed_at = datetime.utcnow()
    answer = {"item_id": state["items"][0]["id"], "value": 3,
              "shown_at": completed_at, "answered_at": completed_at}
    raced = False

    def other_tab_finishes(query, update, *args, **kwargs):
        nonlocal raced
        if "answers.item_id" in query and not raced:
            raced = True
            original_update({"user_id": user["id"]}, {"$set": {
                "status": "completed", "completed_at": completed_at, "answers": [answer],
            }})
        return original_update(query, update, *args, **kwargs)

    monkeypatch.setattr(col, "update_one", other_tab_finishes)
    response = client.post("/surveys/pre_quiz/submit", json={
        "answers": [{"item_id": answer["item_id"], "value": 5}],
    })
    assert response.status_code == 200, response.text
    saved = col.find_one({"user_id": user["id"]})
    assert saved["answers"][0]["value"] == 3
    assert saved["completed_at"] == completed_at.replace(microsecond=(completed_at.microsecond // 1000) * 1000)
    assert client.get("/study/next").json()["next_step"]["id"] == "quiz:base"


@pytest.mark.parametrize("kind,key,collection", [
    ("surveys", "pre_quiz", "survey_responses"), ("quiz", "base", "quiz_attempts"),
])
def test_completed_step_with_missing_data_does_not_create_a_new_attempt(session_app, kind, key, collection):
    client = TestClient(session_app)
    user = signup(client)
    db = session_app.state.db
    db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {
        "completed_steps": ["survey:pre_quiz", "quiz:base"],
    }})
    assert client.get(f"/{kind}/{key}/state").status_code == 409
    if kind == "surveys":
        retry = client.post(f"/{kind}/{key}/submit", json={"answers": []})
    else:
        retry = client.post(f"/{kind}/{key}/answer", json={"question_id": str(ObjectId()), "choice_id": "a"})
    assert retry.status_code == 409
    assert db[collection].count_documents({}) == 0
