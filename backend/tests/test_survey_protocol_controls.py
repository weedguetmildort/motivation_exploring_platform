from datetime import datetime
from bson import ObjectId
import pytest
from tests.test_multi_study import setup, headers
from app.services import study_flow as flow
from app.services.studies import StudyDatabase
from app.services.surveys import create_survey_item, build_survey_state, submit_survey, effective_survey_items
from app.schemas.survey import SurveyItemCreate, SurveySubmitRequest


def item(db, prompt, **kwargs):
    return create_survey_item(db, SurveyItemCreate(stage="post_base", prompt=prompt, **kwargs))


def test_repair_archives_only_extra_variants_and_is_idempotent(setup):
    raw, db, student, _, client = setup
    uid = ObjectId(student.id)
    order = flow.build_step_order(["links", "double", "followup"])
    raw.users.update_one({"_id": uid}, {"$set": {"step_order": order, "completed_steps": order,
        "assigned_var": "double", "variant_sequence": ["links", "double", "followup"], "study_flow_mode": "all_variants",
        "quiz_set_assignment": {"base": "a", "links": "b", "double": "c", "followup": "d"}}})
    for quiz in ("base", "double", "links", "followup"):
        db["quiz_attempts"].insert_one({"user_id": student.id, "quiz_id": quiz, "status": "completed",
            "conversation_id": quiz, "question_order": ["original-question"], "answers": [{"choice_id": "a"}]})
        db["survey_responses"].insert_one({"user_id": student.id, "stage": "post_" + quiz, "status": "completed", "answers": []})
    response = client.get("/auth/me", headers=headers())
    assert response.status_code == 200
    assert response.json()["user"]["step_order"] == flow.build_step_order(["double"])
    assert response.json()["user"]["completed_steps"] == flow.build_step_order(["double"])
    assert db["quiz_attempts"].count_documents({}) == 2
    assert db["quiz_attempt_archive"].count_documents({"archive_reason": "study1_flow_repair"}) == 2
    assert db["survey_response_archive"].count_documents({}) == 2
    assert db["study_flow_repairs"].find_one({"_id": student.id})["original"]["step_order"] == order
    assert db["users"].find_one({"_id": uid})["quiz_set_assignment"]["double"] == "c"
    counters = list(db["counters"].find({}))
    client.get("/auth/me", headers=headers())
    assert db["study_flow_repairs"].count_documents({}) == 1
    assert list(db["counters"].find({})) == counters
    assert db["quiz_attempts"].find_one({"quiz_id": "double"})["question_order"] == ["original-question"]
    from app.services.research_analytics import research_attempts
    assert len(research_attempts(db)) == 2
    assert len(research_attempts(db, include_archived=True)) == 4


def test_named_survey_toggles_are_frozen_per_new_enrollment(setup):
    raw, db, student, _, client = setup
    before = db["users"].find_one({"_id": ObjectId(student.id)})["step_order"]
    settings = {key: {"name": "Named " + key, "enabled": False} for key in flow.survey_stage_settings()}
    result = client.put("/study/config", headers=headers("admin@example.com"), json={"survey_stages": settings})
    assert result.status_code == 200
    assert result.json()["survey_stages"]["post_base"]["enabled"] is False
    assert client.get("/auth/me", headers=headers()).json()["user"]["step_order"] == before
    from app.services.users import create_user
    new = create_user(db["users"], "new@example.com", "pass", "New", "Person", True)
    assert new.step_order == ["quiz:base", "quiz:" + new.assigned_var]
    admin = client.get("/auth/me", headers=headers("admin@example.com")).json()["user"]
    assert len(admin["step_order"]) == 2
    assert admin["study_protocol"]["survey_stages"]["post_base"]["name"] == "Named post_base"
    public_protocol = client.get("/auth/me", headers=headers()).json()["user"]["study_protocol"]
    assert all("name" not in stage for stage in public_protocol["survey_stages"].values())
    assert all("name" in stage for stage in db["users"].find_one({"_id": ObjectId(student.id)})["study_protocol"]["survey_stages"].values())
    assert client.put("/study/config", headers=headers("admin@example.com"), json={"mode": "all_variants"}).status_code == 400


def test_shared_and_specific_items_compose_without_duplicates(setup):
    _, db, _, _, _ = setup
    all_item = item(db, "Every survey", scope="all_surveys")
    common = item(db, "Every post quiz", scope="post_quiz")
    specific = item(db, "Double only", scope="stages", stages=["post_double", "post_double"])
    legacy = item(db, "Legacy shared")
    assert {i.id for i in effective_survey_items(db, "pre_quiz")} == {all_item.id}
    assert {i.id for i in effective_survey_items(db, "post_double")} == {all_item.id, common.id, specific.id, legacy.id}
    assert specific.id not in {i.id for i in effective_survey_items(db, "post_links")}


def test_open_survey_uses_immutable_questions_and_required_ids(setup):
    _, db, student, _, _ = setup
    first = item(db, "Original prompt", scope="stages", stages=["pre_quiz"])
    state = build_survey_state(db, student.id, student.email, "pre_quiz")
    db["survey_items"].delete_one({"_id": ObjectId(first.id)})
    later = item(db, "Added later", scope="all_surveys")
    refreshed = build_survey_state(db, student.id, student.email, "pre_quiz")
    assert [i.model_dump() for i in refreshed.items] == [i.model_dump() for i in state.items]
    saved = submit_survey(db, student.id, student.email, "pre_quiz", SurveySubmitRequest(answers=[{"item_id": first.id, "value": 4}]))
    assert saved.attempt.status == "completed"
    assert saved.items[0].prompt == "Original prompt"
    assert later.id not in [i.id for i in saved.items]
    with pytest.raises(Exception) as error:
        submit_survey(db, student.id, student.email, "post_base", SurveySubmitRequest(answers=[{"item_id": first.id, "value": 4}]))
    assert error.value.status_code == 400


def test_repaired_legacy_final_response_keeps_answers_and_retry_route(setup):
    raw, db, student, _, client = setup
    order = flow.build_step_order(["followup", "double", "links"])
    raw.users.update_one({"_id": ObjectId(student.id)}, {"$set": {"step_order": order, "assigned_var": "followup", "completed_steps": ["survey:post_variant"]}})
    result = db["survey_responses"].insert_one({"user_id": student.id, "stage": "post_variant", "status": "completed", "answers": [], "completed_at": datetime.utcnow()})
    assert client.get("/surveys/post_followup/state", headers=headers()).status_code == 200
    assert db["survey_responses"].find_one({"_id": result.inserted_id})["stage"] == "post_variant"
    assert "survey:post_followup" in client.get("/auth/me", headers=headers()).json()["user"]["completed_steps"]


@pytest.mark.parametrize("invalid", [None, True, "4", 2.5, 0, 6])
def test_likert_values_validate_against_opened_snapshot_before_any_answers_save(setup, invalid):
    _, db, student, _, _ = setup
    first = item(db, "Scale", scope="all_surveys")
    second = item(db, "Other scale", scope="all_surveys")
    build_survey_state(db, student.id, student.email, "pre_quiz")
    with pytest.raises(Exception) as error:
        submit_survey(db, student.id, student.email, "pre_quiz", SurveySubmitRequest(answers=[
            {"item_id": first.id, "value": 4}, {"item_id": second.id, "value": invalid}]))
    assert error.value.status_code == 400
    assert db["survey_responses"].find_one({"user_id": student.id})["answers"] == []
    db["survey_items"].update_many({}, {"$set": {"scale.max": 3}})
    saved = submit_survey(db, student.id, student.email, "pre_quiz", SurveySubmitRequest(answers=[
        {"item_id": first.id, "value": 5}, {"item_id": second.id, "value": 5}]))
    assert saved.attempt.status == "completed"


def test_choice_values_validate_against_original_options_after_an_edit(setup):
    _, db, student, _, _ = setup
    choice = item(db, "Choose", scope="all_surveys", type="single_select", options=[
        {"id": "old-a", "label": "A"}, {"id": "old-b", "label": "B"}])
    build_survey_state(db, student.id, student.email, "pre_quiz")
    db["survey_items"].update_one({"_id": ObjectId(choice.id)}, {"$set": {"options": [
        {"id": "new-a", "label": "New A"}, {"id": "new-b", "label": "New B"}]}})
    with pytest.raises(Exception) as error:
        submit_survey(db, student.id, student.email, "pre_quiz", SurveySubmitRequest(answers=[{"item_id": choice.id, "value": "new-a"}]))
    assert error.value.status_code == 400
    saved = submit_survey(db, student.id, student.email, "pre_quiz", SurveySubmitRequest(answers=[{"item_id": choice.id, "value": "old-a"}]))
    assert saved.attempt.status == "completed"


@pytest.mark.parametrize("retained_complete", [False, True])
def test_study2_prerequisite_uses_repaired_retained_steps(setup, retained_complete, monkeypatch):
    from app.core.config import get_settings
    from app.services.studies import approve_study2
    raw, db, student, admin, client = setup
    monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", "sequential_approval")
    approve_study2(raw, student.id, admin, True)
    retained = flow.build_step_order(["double"])
    raw.users.update_one({"_id": ObjectId(student.id)}, {"$set": {
        "step_order": flow.build_step_order(["links", "double", "followup"]), "assigned_var": "double",
        "completed_steps": retained if retained_complete else retained[:-1]}})
    # Go directly to Study 2: its prerequisite check must perform the repair
    # without first requiring a separate Study 1 login or dashboard visit.
    response = client.get("/studies/study-2/auth/me", headers=headers())
    assert response.status_code == (200 if retained_complete else 403)
    assert db["users"].find_one({"_id": ObjectId(student.id)})["step_order"] == retained


def test_startup_repairs_partial_flow_and_preserves_legacy_flags(setup):
    from app.services.studies import initialize_studies
    raw, db, student, _, client = setup
    raw.users.update_one({"_id": ObjectId(student.id)}, {"$set": {"step_order": flow.build_step_order(["links", "double", "followup"]),
        "assigned_var": None, "variant_sequence": None, "completed_steps": None, "quiz_base_completed": True, "survey_pre_base_completed": True}})
    initialize_studies(raw)
    user = db["users"].find_one({"_id": ObjectId(student.id)})
    assert user["assigned_var"] == "links"
    assert user["completed_steps"] == ["survey:pre_quiz", "quiz:base"]
    raw.users.update_one({"_id": ObjectId(student.id)}, {"$set": {"step_order": None}})
    assert client.get("/auth/me", headers=headers()).status_code == 200


@pytest.mark.parametrize("disabled", ["pre_quiz", "post_base", "post_followup", "post_double", "post_links", "all"])
def test_survey_switches_follow_stable_stage_identity(setup, disabled):
    raw, _, _, _, _ = setup
    db = StudyDatabase(raw, "study-2")
    settings = {key: {"name": key, "enabled": disabled not in (key, "all")} for key in flow.survey_stage_settings()}
    flow.save_study_config(db, survey_stages=settings)
    for _ in range(4):
        assigned = flow.assign_flow(db)
        assert len(flow.quiz_ids_in_order(assigned["step_order"])) == 4
        assert assigned["study_protocol"]["survey_stages"] == settings
        if disabled == "all":
            assert len(assigned["step_order"]) == 4
        else:
            assert "survey:" + disabled not in assigned["step_order"]
            assert len(assigned["step_order"]) == 8


def test_empty_survey_bank_is_not_frozen_into_the_attempt(setup):
    _, db, student, _, _ = setup
    assert build_survey_state(db, student.id, student.email, "pre_quiz").items == []
    added = item(db, "Added after the participant opened the survey", scope="all_surveys")
    state = build_survey_state(db, student.id, student.email, "pre_quiz")
    assert [i.id for i in state.items] == [added.id]
    saved = submit_survey(db, student.id, student.email, "pre_quiz", SurveySubmitRequest(answers=[{"item_id": added.id, "value": 3}]))
    assert saved.attempt.status == "completed"


def test_attempt_that_already_froze_an_empty_bank_recovers(setup):
    _, db, student, _, _ = setup
    build_survey_state(db, student.id, student.email, "pre_quiz")
    db["survey_responses"].update_one({"user_id": student.id, "stage": "pre_quiz"}, {"$set": {"item_snapshot": []}})
    added = item(db, "Added later", scope="all_surveys")
    assert [i.id for i in build_survey_state(db, student.id, student.email, "pre_quiz").items] == [added.id]
