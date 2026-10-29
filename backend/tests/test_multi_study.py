from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import mongomock
import pytest
from bson import ObjectId
from fastapi import FastAPI, HTTPException, Request
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
    from app.api.export import router as export_router
    app.include_router(export_router)
    client = TestClient(app)
    return raw, db, student, str(admin_id), client


@pytest.fixture
def sequential_mode(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", "sequential_approval")


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


def test_admin_only_approval_prerequisite_and_consent(setup, sequential_mode):
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
    assert client.post("/studies/study-2/auth/decline", json={"consent_text": "Study 2 consent"}, headers=headers()).status_code == 200
    status = client.get("/studies/catalog", headers=headers()).json()["studies"][1]
    assert status["consent_required"] is True
    assert client.get("/studies/study-2/surveys/pre_quiz/state", headers=headers()).status_code == 403
    assert client.post("/studies/study-2/auth/consent", json={"consent_text": "Study 2 consent"}, headers=headers()).status_code == 200
    assert client.get("/studies/catalog", headers=headers()).json()["studies"][1]["consent_required"] is False


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
    save_study_config(db, mode="single_variant", questions_per_quiz=7)
    initialize_studies(raw)
    assert db["study_config"].find_one({"_id": "active_flow"})["questions_per_quiz"] == 7
    raw.users.update_one({"_id": ObjectId(student.id)}, {"$unset": {"study_protocol": ""}})
    db["quiz_attempts"].insert_one({"user_id": student.id, "question_order": [str(ObjectId()) for _ in range(4)]})
    doc = snapshot_legacy_protocol(db, db["users"].find_one({"_id": ObjectId(student.id)}))
    assert doc["study_protocol"]["questions_per_quiz"] == 4


def test_environment_overrides_legacy_prerequisite_for_existing_enrollments(setup, monkeypatch):
    from app.core.config import get_settings
    raw, db, student, admin, client = setup
    monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", "sequential_approval")
    approve_study2(raw, student.id, admin, True)
    assert client.get("/studies/study-2/study/next", headers=headers()).status_code == 403
    monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", "independent_approval")
    assert client.get("/studies/study-2/study/next", headers=headers()).status_code == 200


@pytest.mark.parametrize("mode", ["sequential_approval", "sequential", "independent_approval", "independent"])
@pytest.mark.parametrize("finished_first", [False, True])
@pytest.mark.parametrize("approved", [False, True])
def test_access_policy_matrix_catalog_and_direct_api_agree(setup, monkeypatch, mode, finished_first, approved):
    from app.core.config import get_settings, STUDY_ACCESS_MODES
    raw, db, student, admin, client = setup
    monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", mode)
    if finished_first:
        finish_first(raw, student)
    if approved:
        approve_study2(raw, student.id, admin, True)
    first_required, approval_required = STUDY_ACCESS_MODES[mode]
    allowed = (not first_required or finished_first) and (not approval_required or approved)
    catalog = client.get("/studies/catalog", headers=headers()).json()
    assert catalog["access_policy"] == {"mode": mode, "requires_study1_completion": first_required, "requires_approval": approval_required}
    assert catalog["studies"][0]["available"] is True
    assert catalog["studies"][1]["available"] is allowed
    response = client.get("/studies/study-2/auth/me", headers=headers())
    assert response.status_code == (200 if allowed else 403)
    if allowed:
        assert len(response.json()["user"]["step_order"]) == 9
        enrollment = raw.study_enrollments.find_one({"_id": ObjectId(student.id)})
        assert bool(enrollment.get("approved")) is approved
        # Approval-free access still requires fresh, study-specific consent.
        assert client.get("/studies/study-2/surveys/pre_quiz/state", headers=headers()).status_code == 403
        assert client.post("/studies/study-2/auth/consent", json={"consent_text": "Study 2 consent"}, headers=headers()).status_code == 200
        assert client.get("/studies/study-2/study/next", headers=headers()).json()["next_step"]["id"] == "survey:pre_quiz"
    assert raw.users.count_documents({"email": student.email}) == 1


def test_open_enrollment_survives_mode_changes_without_granting_approval(setup, monkeypatch):
    from app.core.config import get_settings
    raw, db, student, admin, client = setup
    monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", "independent")
    assert client.get("/studies/catalog", headers=headers()).json()["studies"][1]["available"]
    assert raw.study_enrollments.count_documents({}) == 0  # Browsing is not enrollment.
    assert client.post("/studies/study-2/studies/start", headers=headers()).status_code == 200
    original = raw.study_enrollments.find_one({"_id": ObjectId(student.id)})
    raw.study_enrollments.update_one({"_id": original["_id"]}, {"$set": {"completed_steps": ["survey:pre_quiz"]}})
    monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", "independent_approval")
    assert client.get("/studies/study-2/auth/me", headers=headers()).status_code == 403
    assert client.get("/studies/catalog", headers=headers()).json()["studies"][1]["completed_steps"] == 1
    approve_study2(raw, student.id, admin, True)
    assert client.get("/studies/study-2/auth/me", headers=headers()).status_code == 200
    approve_study2(raw, student.id, admin, False)
    assert client.get("/studies/study-2/auth/me", headers=headers()).status_code == 403
    monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", "independent")
    assert client.get("/studies/study-2/auth/me", headers=headers()).status_code == 200
    final = raw.study_enrollments.find_one({"_id": original["_id"]})
    assert final["study_protocol"] == original["study_protocol"]
    assert final["completed_steps"] == ["survey:pre_quiz"]
    assert final["approved"] is False
    assert final["access_mode_at_enrollment"] == "independent"


def test_deprecated_api_prerequisite_cannot_override_environment(setup, monkeypatch):
    from app.core.config import get_settings
    raw, db, student, admin, client = setup
    monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", "independent")
    result = client.put("/studies/study-2/study/config", headers=headers("admin@example.com"),
                        json={"requires_study1_completion": True})
    assert result.status_code == 200
    assert result.json()["requires_study1_completion"] is False
    assert result.json()["requires_study2_approval"] is False
    assert result.json()["study_access_mode"] == "independent"


def test_access_mode_validation_and_default(monkeypatch):
    from app.core.config import Settings
    monkeypatch.delenv("STUDY_ACCESS_MODE", raising=False)
    assert Settings().STUDY_ACCESS_MODE == "independent_approval"
    monkeypatch.setenv("STUDY_ACCESS_MODE", " Independent ")
    assert Settings().STUDY_ACCESS_MODE == "independent"
    monkeypatch.setenv("STUDY_ACCESS_MODE", "invalid")
    with pytest.raises(ValueError, match="STUDY_ACCESS_MODE must be one of"):
        Settings()


def test_survey_banks_and_saved_responses_stay_separate(setup):
    raw, db, student, admin, client = setup
    from app.services.surveys import create_survey_item
    from app.schemas.survey import SurveyItemCreate
    item = create_survey_item(db, SurveyItemCreate(stage="pre_quiz", type="likert", prompt="I can use AI", required=True, order=0))
    finish_first(raw, student)
    approve_study2(raw, student.id, admin, True)
    assert client.post("/studies/study-2/auth/consent", json={"consent_text": "Study 2 consent"}, headers=headers()).status_code == 200
    response = client.get("/studies/study-2/surveys/pre_quiz/state", headers=headers())
    assert response.status_code == 200
    second = StudyDatabase(raw, "study-2")
    second["survey_items"].update_one({"_id": ObjectId(item.id)}, {"$set": {"prompt": "Interview version"}})
    assert db["survey_items"].find_one({"_id": ObjectId(item.id)})["prompt"] == "I can use AI"
    assert second["survey_items"].find_one({"_id": ObjectId(item.id)})["prompt"] == "Interview version"
    assert db["survey_responses"].count_documents({}) == 0
    assert second["survey_responses"].count_documents({}) == 1


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


def test_admin_preview_and_messages_use_selected_study(setup):
    raw, db, student, admin, client = setup
    @client.app.get("/scope-probe")
    def probe(request: Request):
        return {"messages": request.app.state.messages.name, "study": request.app.state.db.study_id}
    response = client.get("/studies/study-2/auth/me", headers=headers("admin@example.com"))
    assert response.status_code == 200
    assert response.json()["user"]["consent"] is True
    assert response.json()["user"]["step_order"]
    response = client.get("/studies/study-2/scope-probe", headers=headers("admin@example.com"))
    assert response.json() == {"messages": "study2__messages", "study": "study-2"}


def test_combined_admin_counts_unique_people_and_separate_enrollments(setup):
    from app.services.quiz import _load_or_create_attempt
    import io, json, zipfile
    raw, db, student, admin, client = setup
    raw.questions.insert_one({"stem": "Question", "choices": [{"id": "a", "label": "A"}], "correct_choice_id": "a", "set": "a"})
    approve_study2(raw, student.id, admin, True)
    for sid in ("study-1", "study-2"):
        scoped = StudyDatabase(raw, sid)
        attempt = _load_or_create_attempt(scoped, student.id, student.email, "base", quiz_set="a")
        scoped["quiz_attempts"].update_one({"_id": attempt["_id"]}, {"$set": {"status": "completed", "answers": [
            {"question_id": attempt["question_order"][0], "choice_id": "a", "marked_correct": True,
             "shown_at": datetime.now(timezone.utc), "answered_at": datetime.now(timezone.utc)}]}})
    response = client.get("/research/results?study=all", headers=headers("admin@example.com"))
    assert response.status_code == 200
    data = response.json()
    assert data["matched_accounts"] == 1 and data["matched_enrollments"] == 2
    assert data["overall"]["attempt_count"] == 2
    assert data["overall"]["metrics"]["accuracy"]["participant_count"] == 2
    assert len({p["participant_id"] for p in data["participants"]}) == 2
    for person in data["participants"]:
        detail = client.get(f"/research/participants/{person['participant_id']}", headers=headers("admin@example.com"))
        assert detail.status_code == 200
        assert detail.json()["participant"]["study_id"] == person["study_id"]
    assert client.get("/research/results?study=study-2", headers=headers("admin@example.com")).json()["overall"]["attempt_count"] == 1
    assert client.get("/research/results?study=all", headers=headers()).status_code == 403
    import csv
    exported_csv = client.get("/studies/study-2/export/quiz-answers", headers=headers("admin@example.com"))
    csv_rows = list(csv.DictReader(io.StringIO(exported_csv.text)))
    assert len(csv_rows) == 1 and csv_rows[0]["study_id"] == "study-2"
    assert csv_rows[0]["attempt_id"] == str(raw["study2__quiz_attempts"].find_one({})["_id"])
    variant_csv = client.get("/studies/study-2/export/research-variants", headers=headers("admin@example.com"))
    assert list(csv.DictReader(io.StringIO(variant_csv.text)))[0]["study_id"] == "study-2"
    exported = client.get("/export/research-bundle?study=all", headers=headers("admin@example.com"))
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert "study-2_snapshot.zip" in archive.namelist()
        with zipfile.ZipFile(io.BytesIO(archive.read("study-2_snapshot.zip"))) as snapshot:
            manifest = json.loads(snapshot.read("manifest.json"))
            assert manifest["study_id"] == "study-2"
            assert json.loads(snapshot.read("questions.json"))[0]["study_id"] == "study-2"


def test_interview_search_accepts_a_full_name_and_is_admin_only(setup):
    raw, db, student, admin, client = setup
    assert client.get("/studies/participants?search=Test%20Student", headers=headers()).status_code == 403
    response = client.get("/studies/participants?search=Test%20Student", headers=headers("admin@example.com"))
    assert response.status_code == 200
    assert [p["id"] for p in response.json()["participants"]] == [student.id]


@pytest.fixture
def code_mode(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", "independent_approval")


def rotate(client):
    return client.post("/studies/access-code/rotate", headers=headers("admin@example.com")).json()


def test_access_code_admin_only_and_rotation(setup):
    raw, db, student, admin, client = setup
    assert client.get("/studies/access-code", headers=headers()).status_code == 403
    assert client.post("/studies/access-code/rotate", headers=headers()).status_code == 403
    assert client.get("/studies/access-code", headers=headers("admin@example.com")).json()["code"] is None
    first = rotate(client)
    assert first["version"] == 1 and len(first["code"]) == 9 and first["rotated_by"] == admin
    assert client.get("/studies/access-code", headers=headers("admin@example.com")).json()["code"] == first["code"]
    second = rotate(client)
    assert second["version"] == 2 and second["code"] != first["code"]


def test_one_code_unlocks_many_participants_until_rotated(setup, code_mode):
    raw, db, student, admin, client = setup
    others = [create_user(db["users"], f"s{i}@example.com", "password", "S", str(i), True) for i in range(3)]
    code = rotate(client)["code"]
    assert client.get("/studies/study-2/study/next", headers=headers()).status_code == 403
    for email in ("student@example.com", "s0@example.com", "s1@example.com"):
        # Lowercase and missing dash are accepted; Study 1 is not required in this mode.
        status = client.post("/studies/access-code/redeem", json={"code": code.lower().replace("-", "")},
                             headers=headers(email))
        assert status.status_code == 200 and status.json()["available"] is True
        assert client.get("/studies/study-2/study/next", headers=headers(email)).status_code == 200
    new_code = rotate(client)["code"]
    assert client.post("/studies/access-code/redeem", json={"code": code}, headers=headers("s2@example.com")).status_code == 403
    assert client.post("/studies/access-code/redeem", json={"code": new_code}, headers=headers("s2@example.com")).status_code == 200
    # Rotation never revokes earlier redemptions.
    assert client.get("/studies/study-2/study/next", headers=headers()).status_code == 200
    enrollment = raw.study_enrollments.find_one({"_id": ObjectId(others[2].id)})
    assert enrollment["access_history"][-1] == {**enrollment["access_history"][-1], "via": "access_code",
                                                "code_version": 2, "admin_id": None}
    assert enrollment["enrollment_source"] == "access_code" and enrollment["step_order"]


def test_access_code_keeps_study1_rule_in_sequential_mode(setup, sequential_mode):
    raw, db, student, admin, client = setup
    code = rotate(client)["code"]
    status = client.post("/studies/access-code/redeem", json={"code": code}, headers=headers()).json()
    assert status["approved"] is True and status["available"] is False and status["reason"] == "Complete Study 1 first"
    finish_first(raw, student)
    assert client.get("/studies/study-2/study/next", headers=headers()).status_code == 200


def test_access_code_is_unneeded_when_approval_is_optional(setup, monkeypatch):
    from app.core.config import get_settings
    raw, db, student, admin, client = setup
    monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", "independent")
    response = client.post("/studies/access-code/redeem", json={"code": "anything"}, headers=headers())
    assert response.status_code == 200 and response.json()["available"] is True
    assert raw.study_enrollments.count_documents({}) == 0


def test_redeeming_twice_keeps_frozen_protocol_and_single_audit(setup, code_mode):
    raw, db, student, admin, client = setup
    code = rotate(client)["code"]
    client.post("/studies/access-code/redeem", json={"code": code}, headers=headers())
    before = raw.study_enrollments.find_one({"_id": ObjectId(student.id)})
    assert client.post("/studies/access-code/redeem", json={"code": code}, headers=headers()).status_code == 200
    after = raw.study_enrollments.find_one({"_id": ObjectId(student.id)})
    assert after["step_order"] == before["step_order"] and len(after["access_history"]) == 1


def test_access_code_cannot_bypass_admin_revocation(setup, code_mode):
    raw, db, student, admin, client = setup
    code = rotate(client)["code"]
    client.post("/studies/access-code/redeem", json={"code": code}, headers=headers())
    approve_study2(raw, student.id, admin, False)
    assert client.get("/studies/catalog", headers=headers()).json()["studies"][1]["reason"] == "Study 2 access was revoked. Contact the research team."
    response = client.post("/studies/access-code/redeem", json={"code": code}, headers=headers())
    assert response.status_code == 403 and "revoked" in response.json()["detail"]
    approve_study2(raw, student.id, admin, True)
    assert client.get("/studies/study-2/study/next", headers=headers()).status_code == 200


def test_access_code_rejects_without_active_code_and_limits_guesses(setup, code_mode):
    raw, db, student, admin, client = setup
    assert client.post("/studies/access-code/redeem", json={"code": "ABCD-EFGH"}, headers=headers()).status_code == 403
    code = rotate(client)["code"]
    for _ in range(9):
        assert client.post("/studies/access-code/redeem", json={"code": "WRONG123"}, headers=headers()).status_code == 403
    # The correct code is refused once the failure limit is reached.
    assert client.post("/studies/access-code/redeem", json={"code": code}, headers=headers()).status_code == 429
    assert raw.study_enrollments.count_documents({}) == 0
    raw.study_access_attempts.update_one({"_id": ObjectId(student.id)},
        {"$set": {"window_start": datetime(2000, 1, 1, tzinfo=timezone.utc)}})
    assert client.post("/studies/access-code/redeem", json={"code": code}, headers=headers()).status_code == 200
    assert raw.study_access_attempts.count_documents({}) == 0
    assert client.post("/studies/access-code/redeem", json={"code": ""}, headers=headers()).status_code == 422


def test_access_timestamps_are_labelled_utc(setup, code_mode):
    raw, db, student, admin, client = setup
    assert rotate(client)["rotated_at"].endswith("+00:00")
    assert client.get("/studies/access-code", headers=headers("admin@example.com")).json()["rotated_at"].endswith("+00:00")
    approve_study2(raw, student.id, admin, True, interview_at=datetime(2026, 11, 2, 15, tzinfo=timezone.utc))
    person = client.get("/studies/participants", headers=headers("admin@example.com")).json()["participants"][0]
    # Naive strings are parsed as local time by browsers, shifting saved interview times.
    assert person["interview_at"] == "2026-11-02T15:00:00+00:00"
    assert person["approved_at"].endswith("+00:00") and person["access_history"][0]["at"].endswith("+00:00")


def test_study2_survey_bank_created_first_is_not_merged_with_study1(setup):
    raw, db, student, admin, client = setup
    from app.services.surveys import create_survey_item
    from app.schemas.survey import SurveyItemCreate
    second = StudyDatabase(raw, "study-2")
    own = create_survey_item(second, SurveyItemCreate(stage="pre_quiz", type="likert", prompt="Study 2 only", required=True, order=0))
    create_survey_item(db, SurveyItemCreate(stage="pre_quiz", type="likert", prompt="Study 1 only", required=True, order=0))
    assert [i["_id"] for i in second["survey_items"].find({})] == [ObjectId(own.id)]


# ── Survey bank copy ─────────────────────────────────────────────────────────

def _study1_items(raw, count=3):
    return raw.survey_items.insert_many([{"stage": "pre_quiz", "type": "likert", "prompt": f"Item {i}",
                                          "required": True, "order": i} for i in range(count)]).inserted_ids


def test_interrupted_survey_bank_copy_resumes_instead_of_locking_in(setup):
    from app.services.studies import initialize_survey_bank
    raw = setup[0]
    ids = _study1_items(raw)
    # A copy that crashed after its first item: the marker says it began.
    raw.study2__study_config.insert_one({"_id": "survey_bank_copy_started"})
    raw.study2__survey_items.insert_one({**raw.survey_items.find_one({"_id": ids[0]}), "study_id": "study-2"})
    initialize_survey_bank(raw)
    assert sorted(i["_id"] for i in raw.study2__survey_items.find({})) == sorted(ids)
    assert raw.study2__study_config.find_one({"_id": "survey_bank_initialized"})


def test_survey_bank_copy_records_its_start_and_never_overwrites_study2_edits(setup):
    from app.services.studies import initialize_survey_bank
    raw = setup[0]
    ids = _study1_items(raw, 2)
    initialize_survey_bank(raw)
    assert raw.study2__study_config.find_one({"_id": "survey_bank_copy_started"})
    raw.study2__survey_items.update_one({"_id": ids[0]}, {"$set": {"prompt": "Edited for Study 2"}})
    raw.study2__study_config.delete_one({"_id": "survey_bank_initialized"})
    initialize_survey_bank(raw)
    assert raw.study2__survey_items.find_one({"_id": ids[0]})["prompt"] == "Edited for Study 2"
    assert raw.study2__survey_items.count_documents({}) == 2


# ── Startup ──────────────────────────────────────────────────────────────────

def test_failed_failure_records_expire_with_the_lockout_window():
    raw = mongomock.MongoClient().db
    initialize_studies(raw)
    index = next(i for i in raw.study_access_attempts.index_information().values() if i["key"] == [("window_start", 1)])
    assert index["expireAfterSeconds"] == 900


def test_one_failing_startup_repair_does_not_stop_the_app(monkeypatch, caplog):
    from app.services import study_repair
    raw = mongomock.MongoClient().db
    broken = raw.users.insert_one({"email": "x@example.com", "step_order": ["quiz:followup", "quiz:double"]}).inserted_id
    def explode(db, user):
        raise RuntimeError("bad legacy document")
    monkeypatch.setattr(study_repair, "repair_study1_flow", explode)
    initialize_studies(raw)
    assert str(broken) in caplog.text and "Startup repair failed" in caplog.text


# ── Access-code and approval edge cases ──────────────────────────────────────

def test_saving_interview_details_keeps_how_access_was_first_granted(setup, code_mode):
    raw, db, student, admin, client = setup
    code = rotate(client)["code"]
    client.post("/studies/access-code/redeem", json={"code": code}, headers=headers())
    granted = raw.study_enrollments.find_one({"_id": ObjectId(student.id)})
    interview = datetime(2026, 11, 3, 14, tzinfo=timezone.utc)
    approve_study2(raw, student.id, admin, True, interview_at=interview, notes="Room 2")
    saved = raw.study_enrollments.find_one({"_id": ObjectId(student.id)})
    assert saved["approved_by"] == "access_code" and saved["approved_at"] == granted["approved_at"]
    assert saved["access_code_version"] == 1
    assert saved["interviewer_notes"] == "Room 2" and saved["interview_at"].replace(tzinfo=timezone.utc) == interview
    # The audit trail still records both changes.
    assert [h.get("via") or h["admin_id"] for h in saved["access_history"]] == ["access_code", admin]


def test_admin_reapproval_lifts_a_revocation(setup, code_mode):
    raw, db, student, admin, client = setup
    approve_study2(raw, student.id, admin, True)
    approve_study2(raw, student.id, admin, False)
    revoked = client.get("/studies/catalog", headers=headers()).json()["studies"][1]
    assert revoked["revoked"] is True and revoked["code_required"] is False and revoked["available"] is False
    approve_study2(raw, student.id, admin, True)
    enrollment = raw.study_enrollments.find_one({"_id": ObjectId(student.id)})
    assert "revoked_at" not in enrollment and "revoked_by" not in enrollment and enrollment["approved"] is True
    status = client.get("/studies/catalog", headers=headers()).json()["studies"][1]
    assert status["revoked"] is False and status["available"] is True


def test_revoking_access_before_approval_keeps_the_code_blocked(setup, code_mode):
    raw, db, student, admin, client = setup
    code = rotate(client)["code"]
    approve_study2(raw, student.id, admin, False)
    response = client.post("/studies/access-code/redeem", json={"code": code}, headers=headers())
    assert response.status_code == 403 and "Contact the research team" in response.json()["detail"]
    # A blocked attempt is not a guess: it never counts toward the lockout.
    assert raw.study_access_attempts.count_documents({}) == 0


def test_a_revocation_during_redemption_wins(setup, code_mode, monkeypatch):
    from app.services import studies as service
    raw, db, student, admin, client = setup
    code = rotate(client)["code"]
    enroll = service.ensure_study2_enrollment
    def enroll_then_revoke(raw_db, user, source="self_enrollment"):
        enroll(raw_db, user, source)
        approve_study2(raw_db, student.id, admin, False)
    monkeypatch.setattr(service, "ensure_study2_enrollment", enroll_then_revoke)
    response = client.post("/studies/access-code/redeem", json={"code": code}, headers=headers())
    assert response.status_code == 403 and "revoked" in response.json()["detail"]
    enrollment = raw.study_enrollments.find_one({"_id": ObjectId(student.id)})
    assert enrollment["approved"] is False and [h["approved"] for h in enrollment["access_history"]] == [False]


def test_every_attempt_counts_before_the_code_is_compared(setup, code_mode):
    raw, db, student, admin, client = setup
    code = rotate(client)["code"]
    statuses = [client.post("/studies/access-code/redeem", json={"code": "WRONG123"}, headers=headers()).status_code
                for _ in range(12)]
    assert statuses == [403] * 10 + [429] * 2
    assert raw.study_access_attempts.find_one({"_id": ObjectId(student.id)})["failures"] == 12
    assert client.post("/studies/access-code/redeem", json={"code": code}, headers=headers()).status_code == 429


def test_parallel_guesses_cannot_exceed_the_limit(setup, code_mode):
    from app.services.studies import redeem_access_code, MAX_CODE_FAILURES
    raw, db, student, admin, client = setup
    rotate(client)
    user = raw.users.find_one({"_id": ObjectId(student.id)})
    def guess(_):
        try:
            redeem_access_code(raw, user, "WRONG123")
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(guess, range(40)))
    assert statuses.count(403) == MAX_CODE_FAILURES and statuses.count(429) == 40 - MAX_CODE_FAILURES


@pytest.mark.parametrize("elapsed,left", [(timedelta(minutes=10), "5 minutes"), (timedelta(minutes=14, seconds=30), "1 minute")])
def test_lockout_message_reports_the_time_actually_left(setup, code_mode, elapsed, left):
    raw, db, student, admin, client = setup
    rotate(client)
    raw.study_access_attempts.insert_one({"_id": ObjectId(student.id), "failures": 10,
                                          "window_start": datetime.now(timezone.utc) - elapsed})
    response = client.post("/studies/access-code/redeem", json={"code": "WRONG123"}, headers=headers())
    assert response.status_code == 429 and response.json()["detail"] == f"Too many incorrect codes. Try again in {left}."


def test_an_approved_participant_who_was_locked_out_gets_their_status(setup, code_mode):
    raw, db, student, admin, client = setup
    rotate(client)
    for _ in range(11):
        client.post("/studies/access-code/redeem", json={"code": "WRONG123"}, headers=headers())
    approve_study2(raw, student.id, admin, True)
    response = client.post("/studies/access-code/redeem", json={"code": "WRONG123"}, headers=headers())
    assert response.status_code == 200 and response.json()["available"] is True


def test_catalog_says_when_a_code_is_the_way_in(setup, code_mode, monkeypatch):
    from app.core.config import get_settings
    raw, db, student, admin, client = setup
    second = lambda email="student@example.com": client.get("/studies/catalog", headers=headers(email)).json()["studies"][1]
    assert second()["code_required"] is True and second()["revoked"] is False
    assert second("admin@example.com")["code_required"] is False
    client.post("/studies/access-code/redeem", json={"code": rotate(client)["code"]}, headers=headers())
    assert second()["code_required"] is False
    monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", "independent")
    other = create_user(db["users"], "open@example.com", "password", "Open", "Mode", True)
    assert second(other.email)["code_required"] is False


def test_direct_study2_requests_point_to_the_code_or_the_revocation(setup, code_mode):
    raw, db, student, admin, client = setup
    response = client.get("/studies/study-2/study/next", headers=headers())
    assert response.status_code == 403 and response.json()["detail"] == "Enter the Study 2 access code from your interviewer"
    approve_study2(raw, student.id, admin, False)
    response = client.get("/studies/study-2/study/next", headers=headers())
    assert response.json()["detail"] == "Study 2 access was revoked. Contact the research team."


# ── Study 2 assignment ───────────────────────────────────────────────────────

def test_study2_enrollment_honours_a_pinned_variant_and_leaves_study1_alone(setup):
    from app.services.users import set_next_assignment_override, peek_next_assignment
    raw, db, student, admin, client = setup
    second = StudyDatabase(raw, "study-2")
    set_next_assignment_override(second["users"], "links")
    set_next_assignment_override(db["users"], "double")
    assert peek_next_assignment(second["users"]) == {"next": "links", "source": "override"}
    approve_study2(raw, student.id, admin, True)
    enrollment = raw.study_enrollments.find_one({"_id": ObjectId(student.id)})
    assert enrollment["variant_sequence"][0] == "links" and enrollment["assignment_source"] == "override"
    assert peek_next_assignment(second["users"])["source"] == "rotation"
    assert peek_next_assignment(db["users"]) == {"next": "double", "source": "override"}


# ── Admin previews ───────────────────────────────────────────────────────────

def test_study2_admin_preview_records_the_live_access_policy(setup, code_mode):
    raw, db, student, admin, client = setup
    user = client.get("/studies/study-2/auth/me", headers=headers("admin@example.com")).json()["user"]
    assert user["study_protocol"]["requires_study1_completion"] is False
    assert user["study_protocol"]["study_access_mode"] == "independent_approval"
    assert user["study_protocol"]["requires_study2_approval"] is True


def test_admin_previews_draw_sets_like_participants_without_claiming_slots(setup):
    raw, db, student, admin, client = setup
    second = client.get("/studies/study-2/auth/me", headers=headers("admin@example.com")).json()["user"]
    quizzes = [step.split(":", 1)[1] for step in second["step_order"] if step.startswith("quiz:")]
    sets = second["quiz_set_assignment"]
    assert sorted(sets) == sorted(quizzes) and len(set(sets.values())) == len(quizzes)
    assert not any(c["_id"].startswith("quiz_sets:") for c in raw.study2__counters.find({}))
    # Stable across requests once drawn.
    again = client.get("/studies/study-2/auth/me", headers=headers("admin@example.com")).json()["user"]
    assert again["quiz_set_assignment"] == sets
    # Study 1 uses its preset map, which is empty: every quiz draws from the whole pool.
    first = client.get("/auth/me", headers=headers("admin@example.com")).json()["user"]
    assert first["quiz_set_assignment"] == {}


def test_study1_admin_preview_follows_the_preset_map(setup):
    raw, db, student, admin, client = setup
    save_study_config(db, quiz_set_map={"base": "c"})
    first = client.get("/auth/me", headers=headers("admin@example.com")).json()["user"]
    assert first["quiz_set_assignment"] == {"base": "c"}


# ── Users wrapper ────────────────────────────────────────────────────────────

def test_study2_users_wrapper_sorts_projects_and_hides_unenrolled_people(setup):
    raw, db, student, admin, client = setup
    people = [create_user(db["users"], f"{name}@example.com", "password", name, "P", True) for name in ("amy", "zoe", "bob")]
    for person in people[:2]:
        approve_study2(raw, person.id, admin, True)
    users = StudyDatabase(raw, "study-2")["users"]
    found = list(users.find({"is_admin": {"$ne": True}}, {"email": 1}).sort("email", -1))
    assert found == [{"_id": ObjectId(people[1].id), "email": "zoe@example.com"},
                     {"_id": ObjectId(people[0].id), "email": "amy@example.com"}]
    assert users.find_one({"_id": ObjectId(people[0].id)}, {"step_order": 0})["completed_steps"] == []
    assert "step_order" not in users.find_one({"_id": ObjectId(people[0].id)}, {"step_order": 0})
    assert users.find_one({"_id": ObjectId(people[2].id)}) is None
    assert users.count_documents({"email": "bob@example.com"}) == 0


def test_study1_users_wrapper_applies_projections(setup):
    raw, db, student, admin, client = setup
    assert db["users"].find_one({"_id": ObjectId(student.id)}, {"email": 1}) == {
        "_id": ObjectId(student.id), "email": "student@example.com", "study_id": "study-1"}
    assert [u["email"] for u in db["users"].find({"is_admin": False}, {"email": 1})] == ["student@example.com"]


# ── Middleware and endpoints ─────────────────────────────────────────────────

def test_study2_requests_do_not_touch_study1_progress(setup, code_mode):
    raw, db, student, admin, client = setup
    approve_study2(raw, student.id, admin, True)
    raw.users.update_one({"_id": ObjectId(student.id)}, {"$unset": {"step_order": "", "completed_steps": ""}})
    assert client.get("/studies/study-2/study/next", headers=headers()).status_code == 200
    assert "step_order" not in raw.users.find_one({"_id": ObjectId(student.id)})


def test_study2_requests_still_reject_unknown_sessions(setup):
    client = setup[4]
    assert client.get("/studies/study-2/study/next").status_code == 401
    assert client.get("/studies/study-2/study/next", headers=headers("nobody@example.com")).status_code == 401


def test_flow_reports_each_studys_quiz_structure(setup, code_mode):
    raw, db, student, admin, client = setup
    assert client.get("/study/flow", headers=headers()).json()["mode"] == "single_variant"
    approve_study2(raw, student.id, admin, True)
    assert client.get("/studies/study-2/study/flow", headers=headers()).json()["mode"] == "all_variants"


def test_chat_message_export_holds_ai_replies_only(setup):
    import csv
    import io
    raw, db, student, admin, client = setup
    raw.messages.insert_many([
        {"role": "user", "content": "Is it B?", "user_id": student.id, "created_at": datetime(2026, 1, 1)},
        {"role": "assistant", "content": "It is B.", "user_id": student.id, "created_at": datetime(2026, 1, 2),
         "model_version": "gpt-4.1"},
    ])
    response = client.get("/export/chat-messages", headers=headers("admin@example.com"))
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert [row["content"] for row in rows] == ["It is B."] and rows[0]["model_version"] == "gpt-4.1"
    assert "role" not in rows[0] and "intent_labels_heuristic" not in rows[0]
