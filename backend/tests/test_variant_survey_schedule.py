from bson import ObjectId
import pytest
from tests.test_multi_study import setup, headers, finish_first
from app.services import study_flow as flow
from app.services.studies import StudyDatabase, approve_study2
from app.services.users import create_user
from app.services.surveys import create_survey_item
from app.schemas.survey import SurveyItemCreate


@pytest.mark.parametrize("sid,count", [("study-1", 2), ("study-2", 4)])
@pytest.mark.parametrize("mode", ["end_only", "per_variant"])
def test_both_studies_choose_grouping_without_changing_enrolled_schedules(setup, sid, count, mode):
    raw, _, student, _, _ = setup
    db = StudyDatabase(raw, sid)
    old = raw.users.find_one({"_id": ObjectId(student.id)})
    config = flow.save_study_config(db, variant_survey_mode=mode)
    assigned = flow.assign_flow(db)
    assert len(flow.quiz_ids_in_order(assigned["step_order"])) == count
    assert assigned["study_protocol"]["variant_survey_mode"] == mode
    if mode == "end_only":
        assert assigned["step_order"][-1] == "survey:post_variant"
        assert len(assigned["step_order"]) == count + 3
    else:
        assert "survey:post_variant" not in assigned["step_order"]
        assert len(assigned["step_order"]) == 2 * count + 1
    assert raw.users.find_one({"_id": ObjectId(student.id)})["step_order"] == old["step_order"]
    disabled = {key: {**value, "enabled": False} for key, value in flow.survey_stage_settings(config.survey_stages).items()}
    flow.save_study_config(db, survey_stages=disabled)
    assert len(flow.assign_flow(db)["step_order"]) == count


def test_new_study1_defaults_to_legacy_final_stage_without_rewriting_existing_schedule(setup):
    raw, db, student, _, client = setup
    assert student.step_order[-1] == "survey:post_variant"
    raw.users.update_one({"_id": ObjectId(student.id)}, {"$set": {
        "step_order": flow.build_step_order([student.assigned_var.value]),
        "study_protocol.variant_survey_mode": "per_variant"}})
    flow.save_study_config(db, variant_survey_mode="end_only")
    current = client.get("/auth/me", headers=headers()).json()["user"]
    assert current["step_order"][-1] == f"survey:post_{student.assigned_var.value}"
    fresh = create_user(db["users"], "fresh@example.com", "password", "Fresh", "Student", True)
    assert fresh.step_order[-1] == "survey:post_variant"


def test_disabling_only_combined_final_finishes_after_last_quiz(setup):
    raw, _, _, _, _ = setup
    db = StudyDatabase(raw, "study-2")
    flow.save_study_config(db, variant_survey_mode="end_only", survey_stages={"post_variant": {"name": "Overall", "enabled": False}})
    person = flow.assign_flow(db)
    assert len(person["step_order"]) == 6
    assert person["step_order"][-1].startswith("quiz:")
    assert flow.next_step_id_from(person["step_order"], person["step_order"]) is None


@pytest.mark.parametrize("sid", ["study-1", "study-2"])
def test_final_survey_composes_only_assigned_variants_and_completes_once(setup, sid):
    raw, _, student, admin, client = setup
    db = StudyDatabase(raw, sid)
    flow.save_study_config(db, variant_survey_mode="end_only")
    if sid == "study-2":
        finish_first(raw, student)
        approve_study2(raw, student.id, admin, True)
        assert client.post("/studies/study-2/auth/consent", headers=headers(), json={"consent_text": "Study consent"}).status_code == 200
    person = db["users"].find_one({"_id": ObjectId(student.id)})
    variants = person["variant_sequence"]
    items = {}
    for target in ["all_surveys", "post_quiz", "post_variant", *["post_" + v for v in flow.all_variants()]]:
        common = target in ("all_surveys", "post_quiz")
        item = create_survey_item(db, SurveyItemCreate(stage="pre_quiz" if common else target,
            scope=target if common else "stages", stages=[] if common else [target], prompt=target))
        items[target] = item.id
    db["users"].update_one({"_id": person["_id"]}, {"$set": {"completed_steps": person["step_order"][:-1]}})
    base_path = f"/studies/{sid}"
    state = client.get(base_path + "/surveys/post_variant/state", headers=headers())
    assert state.status_code == 200, state.text
    expected = {items[key] for key in ["all_surveys", "post_quiz", "post_variant", *["post_" + v for v in variants]]}
    assert {item["id"] for item in state.json()["items"]} == expected
    saved = db["survey_responses"].find_one({"user_id": student.id, "stage": "post_variant"})
    assert saved["covered_quiz_ids"] == variants
    assert "survey:post_variant" not in client.get(base_path + "/auth/me", headers=headers()).json()["user"]["completed_steps"]
    payload = {"answers": [{"item_id": item_id, "value": 4} for item_id in expected]}
    assert client.post(base_path + "/surveys/post_variant/submit", headers=headers(), json=payload).status_code == 200
    retry = client.post(base_path + "/surveys/post_variant/submit", headers=headers(), json={"answers": []})
    assert retry.status_code == 200 and retry.json()["attempt"]["status"] == "completed"
    assert client.get(base_path + "/study/next", headers=headers()).json()["finished"] is True
    import csv
    import io
    import json
    exported = client.get(base_path + "/export/survey-responses", headers=headers("admin@example.com"))
    assert exported.status_code == 200
    records = list(csv.DictReader(io.StringIO(exported.text)))
    assert all(json.loads(record["covered_quiz_ids"]) == variants for record in records)
