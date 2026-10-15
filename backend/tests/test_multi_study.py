from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import mongomock
import pytest
from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.api import auth, studies, study, quiz, surveys, research
from app.core.study_middleware import StudyMiddleware
from app.core.security import create_access_token
from app.services.studies import (StudyDatabase, initialize_studies, approve_study2,
    check_access, enrollment_status, snapshot_legacy_protocol)
from app.services.users import create_user
from app.services.study_flow import save_study_config


@pytest.fixture
def setup():
    raw = mongomock.MongoClient().db
    initialize_studies(raw)
    db = StudyDatabase(raw, "study-1")
    student = create_user(db["users"], "student@example.com", "password", "Test", "Student", True)
    admin_id = raw.users.insert_one({"email": "admin@example.com", "is_admin": True}).inserted_id
    app = FastAPI()
    app.state.raw_db, app.state.db = raw, db
    app.add_middleware(StudyMiddleware)
    for module in (auth, studies, study, quiz, surveys, research):
        app.include_router(module.router)
    client = TestClient(app)
    return raw, db, student, str(admin_id), client


def headers(email="student@example.com"):
    return {"Cookie": "session=" + create_access_token(email)}


def finish_first(raw, student):
    doc = raw.users.find_one({"_id": ObjectId(student.id)})
    raw.users.update_one({"_id": doc["_id"]}, {"$set": {"completed_steps": doc["step_order"], "progress_reconciled_version": 1}})


def test_open_first_and_locked_second_every_endpoint(setup):
    raw, db, student, admin, client = setup
    assert client.get("/study/next", headers=headers()).status_code == 200
    for method, path in (("get", "/study/next"), ("get", "/auth/me"), ("get", "/quiz/base/state"),
                         ("post", "/quiz/base/answer"), ("get", "/surveys/pre_quiz/state"),
                         ("post", "/chat/followup"), ("post", "/research/events")):
        assert getattr(client, method)("/studies/study-2" + path, headers=headers()).status_code == 403
    assert raw.study_enrollments.count_documents({}) == 0


def test_admin_only_approval_prerequisite_and_consent(setup):
    raw, db, student, admin, client = setup
    path = f"/studies/participants/{student.id}/study-2-access"
    assert client.patch(path, json={"approved": True}, headers=headers()).status_code == 403
    assert client.patch(path, json={"approved": True}, headers=headers("admin@example.com")).status_code == 200
    assert client.get("/studies/study-2/study/next", headers=headers()).status_code == 403
    finish_first(raw, student)
    assert client.get("/studies/study-2/auth/me", headers=headers()).json()["user"]["completed_steps"] == []
    assert client.get("/studies/study-2/surveys/pre_quiz/state", headers=headers()).status_code == 403
    consent = client.post("/studies/study-2/auth/consent", json={"consent_text": "Study 2 consent"}, headers=headers())
    assert consent.status_code == 200
    assert raw.study_enrollments.find_one({"_id": ObjectId(student.id)})["consent"] is True
    assert raw.users.find_one({"_id": ObjectId(student.id)}).get("consent_text") is None


def test_regrant_preserves_protocol_progress_and_audit(setup):
    raw, db, student, admin, client = setup
    approve_study2(raw, student.id, admin, True, notes="Initial interview")
    initial = raw.study_enrollments.find_one({"_id": ObjectId(student.id)})
    raw.study_enrollments.update_one({"_id": initial["_id"]}, {"$set": {"completed_steps": ["survey:pre_quiz"]}})
    approve_study2(raw, student.id, admin, False)
    assert client.get("/studies/study-2/study/next", headers=headers()).status_code == 403
    save_study_config(StudyDatabase(raw, "study-2"), questions_per_quiz=8)
    approve_study2(raw, student.id, admin, True)
    final = raw.study_enrollments.find_one({"_id": initial["_id"]})
    assert final["completed_steps"] == ["survey:pre_quiz"]
    assert final["study_protocol"]["questions_per_quiz"] == 5
    assert [h["approved"] for h in final["access_history"]] == [True, False, True]
    assert final["approved_by"] == admin
    assert raw.users.find_one({"_id": initial["_id"]})["is_admin"] is False


def test_revoke_before_first_approval_still_initializes_flow(setup):
    raw, db, student, admin, _ = setup
    approve_study2(raw, student.id, admin, False)
    approve_study2(raw, student.id, admin, True)
    assert len(raw.study_enrollments.find_one({"_id": ObjectId(student.id)})["step_order"]) == 9


def test_one_identity_two_progress_and_namespaces(setup):
    raw, db, student, admin, client = setup
    finish_first(raw, student)
    approve_study2(raw, student.id, admin, True)
    second = StudyDatabase(raw, "study-2")
    second["users"].update_one({"_id": ObjectId(student.id)}, {"$set": {"completed_steps": ["survey:pre_quiz"]}})
    second["users"].update_one({"_id": ObjectId(student.id)}, {"$set": {"first_name": "Shared name"}})
    assert db["users"].find_one({"_id": ObjectId(student.id)})["first_name"] == "Shared name"
    assert len(db["users"].find_one({"_id": ObjectId(student.id)})["completed_steps"]) == 5
    assert second["users"].find_one({"_id": ObjectId(student.id)})["completed_steps"] == ["survey:pre_quiz"]
    db["quiz_attempts"].insert_one({"user_id": student.id, "quiz_id": "base"})
    second["quiz_attempts"].insert_one({"user_id": student.id, "quiz_id": "base"})
    assert db["quiz_attempts"].count_documents({}) == second["quiz_attempts"].count_documents({}) == 1
    assert second["users"].database["counters"].name == "study2__counters"
    assert raw.users.count_documents({"email": student.email}) == 1


def test_parallel_requests_do_not_switch_global_database(setup):
    raw, db, student, admin, client = setup
    finish_first(raw, student)
    approve_study2(raw, student.id, admin, True)
    def read(index):
        sid = "study-2" if index % 2 else "study-1"
        response = client.get(f"/studies/{sid}/auth/me", headers=headers())
        assert response.status_code == 200
        assert response.json()["user"]["study_id"] == sid
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(read, range(16)))
    assert client.app.state.db.study_id == "study-1"


def test_existing_config_and_drawn_size_are_preserved(setup):
    raw, db, student, _, _ = setup
    save_study_config(db, mode="all_variants", questions_per_quiz=7)
    initialize_studies(raw)
    assert db["study_config"].find_one({"_id": "active_flow"})["questions_per_quiz"] == 7
    raw.users.update_one({"_id": ObjectId(student.id)}, {"$unset": {"study_protocol": ""}})
    db["quiz_attempts"].insert_one({"user_id": student.id, "question_order": [str(ObjectId()) for _ in range(4)]})
    doc = snapshot_legacy_protocol(db, db["users"].find_one({"_id": ObjectId(student.id)}))
    assert doc["study_protocol"]["questions_per_quiz"] == 4


def test_prerequisite_can_be_disabled_for_future_enrollments(setup):
    raw, db, student, admin, client = setup
    save_study_config(StudyDatabase(raw, "study-2"), requires_study1_completion=False)
    approve_study2(raw, student.id, admin, True)
    assert client.get("/studies/study-2/study/next", headers=headers()).status_code == 200


def test_quiz_size_and_wrong_advice_are_frozen_per_enrollment(setup):
    from app.services.quiz import _load_or_create_attempt
    raw, db, student, admin, _ = setup
    for i in range(16):
        raw.questions.insert_one({"stem": f"Question {i}", "choices": [{"id": "a", "label": "A"}], "correct_choice_id": "a", "set": "a"})
    second = StudyDatabase(raw, "study-2")
    save_study_config(second, wrong_ai_rate=.4, wrong_ai_rate_supplied=True)
    approve_study2(raw, student.id, admin, True)
    save_study_config(second, questions_per_quiz=9, wrong_ai_rate=.8, wrong_ai_rate_supplied=True)
    first = _load_or_create_attempt(db, student.id, student.email, "base", quiz_set="a")
    other = _load_or_create_attempt(second, student.id, student.email, "base", quiz_set="a")
    assert len(first["question_order"]) == 10
    assert len(other["question_order"]) == 5
    assert len(first["incorrect_question_ids"]) == 3
    assert len(other["incorrect_question_ids"]) == 2
    assert other["study_protocol"]["wrong_ai_rate"] == .4
    assert other["study_id"] == "study-2"
