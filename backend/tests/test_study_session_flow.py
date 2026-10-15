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
