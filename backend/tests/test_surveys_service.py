# backend/tests/test_surveys_service.py
"""Unit tests for app/services/surveys.py: collection accessors, index creation,
survey item CRUD, and the user-flow trio (build_survey_state, record_item_shown,
submit_survey)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock
from bson import ObjectId
import pytest
from fastapi import HTTPException

from app.services.surveys import (
    get_survey_items_collection,
    get_survey_responses_collection,
    get_users_collection,
    ensure_survey_indexes,
    _validate_stage,
    _item_to_public,
    _normalize_item_doc,
    create_survey_item,
    list_survey_items,
    update_survey_item,
    delete_survey_item,
    build_survey_state,
    record_item_shown,
    submit_survey,
)
from app.schemas.survey import (
    SurveyItemCreate,
    SurveyItemUpdate,
    SurveySubmitRequest,
    SurveyAnswerIn,
)
from app.schemas.user import SurveyStage
from app.services import study_flow


# ── collection accessors ─────────────────────────────────────────────────────

class TestCollectionAccessors:
    def test_get_survey_items_collection(self, mock_db, mock_col):
        assert get_survey_items_collection(mock_db) is mock_col

    def test_get_survey_responses_collection(self, mock_db, mock_col):
        assert get_survey_responses_collection(mock_db) is mock_col

    def test_get_users_collection(self, mock_db, mock_col):
        assert get_users_collection(mock_db) is mock_col


# ── ensure_survey_indexes ────────────────────────────────────────────────────

class TestEnsureSurveyIndexes:
    def test_creates_indexes_on_items_and_responses(self, mock_db, mock_col):
        ensure_survey_indexes(mock_db)

        # Both collections resolve to mock_col, so create_index is called twice
        assert mock_col.create_index.call_count == 2

        calls = mock_col.create_index.call_args_list
        items_call = calls[0][0][0]
        responses_call = calls[1][0][0]

        assert items_call == [("stage", 1), ("active", 1), ("order", 1)]
        assert responses_call == [("user_id", 1), ("stage", 1)]

        # responses index should be unique
        assert calls[1][1].get("unique") is True


# ── stage helpers ────────────────────────────────────────────────────────────
#
# _next_stage and _completion_flag_field were fixed 3-stage maps; the flow now
# schedules one survey per variant, so stage validation and question sourcing
# are delegated to the study_flow registry.

class TestValidateStage:
    def test_accepts_the_fixed_stages(self):
        assert _validate_stage("pre_quiz") == "pre_quiz"
        assert _validate_stage("post_base") == "post_base"

    def test_accepts_a_per_variant_stage(self):
        stage = study_flow.post_variant_stage(study_flow.all_variants()[0])
        assert _validate_stage(stage) == stage

    def test_still_accepts_the_legacy_post_variant_stage(self):
        """Historical survey_responses docs must stay readable."""
        assert _validate_stage("post_variant") == "post_variant"

    def test_rejects_an_unknown_stage(self):
        with pytest.raises(HTTPException) as exc:
            _validate_stage("not_a_stage")
        assert exc.value.status_code == 400


# ── _item_to_public / _normalize_item_doc ────────────────────────────────────

class TestItemToPublic:
    def test_converts_id_field(self):
        oid = ObjectId()
        doc = {
            "_id": oid,
            "stage": "pre_quiz",
            "prompt": "How motivated are you?",
            "type": "likert",
            "required": True,
            "order": 0,
            "active": True,
            "category": None,
            "reverse_scored": False,
            "scale": {"min": 1, "max": 5, "anchors": ["Strongly disagree", "Strongly agree"]},
            "options": None,
        }

        pub = _item_to_public(doc)

        assert pub.id == str(oid)
        assert pub.prompt == "How motivated are you?"
        assert pub.type == "likert"


class TestNormalizeItemDoc:
    def test_likert_without_scale_gets_default_scale(self):
        doc = {"type": "likert", "stage": "pre_quiz", "prompt": "p"}
        normalized = _normalize_item_doc(doc)

        assert normalized["scale"] == {
            "min": 1,
            "max": 5,
            "anchors": ["Strongly disagree", "Strongly agree"],
        }
        assert normalized["options"] is None

    def test_likert_with_existing_scale_preserved(self):
        doc = {
            "type": "likert",
            "stage": "pre_quiz",
            "prompt": "p",
            "scale": {"min": 0, "max": 10, "anchors": None},
        }
        normalized = _normalize_item_doc(doc)
        assert normalized["scale"] == {"min": 0, "max": 10, "anchors": None}
        assert normalized["options"] is None

    def test_single_select_normalizes_options(self):
        doc = {
            "type": "single_select",
            "stage": "pre_quiz",
            "prompt": "p",
            "options": [
                {"id": "a", "label": "  Yes  "},
                {"id": "b", "label": "No"},
                {"id": "c", "label": "   "},  # empty after strip -> dropped
            ],
        }
        normalized = _normalize_item_doc(doc)

        assert normalized["scale"] is None
        assert normalized["options"] == [
            {"id": "a", "label": "Yes"},
            {"id": "b", "label": "No"},
        ]

    def test_single_select_with_fewer_than_2_valid_options_raises_400(self):
        doc = {
            "type": "single_select",
            "stage": "pre_quiz",
            "prompt": "p",
            "options": [{"id": "a", "label": "Only one"}],
        }
        with pytest.raises(HTTPException) as exc_info:
            _normalize_item_doc(doc)
        assert exc_info.value.status_code == 400

    def test_unknown_type_raises_400(self):
        doc = {"type": "weird_type", "stage": "pre_quiz", "prompt": "p"}
        with pytest.raises(HTTPException) as exc_info:
            _normalize_item_doc(doc)
        assert exc_info.value.status_code == 400


# ── create_survey_item ───────────────────────────────────────────────────────

class TestCreateSurveyItem:
    def test_creates_likert_item(self, mock_db, mock_col):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        data = SurveyItemCreate(stage="pre_quiz", prompt="How motivated are you?")
        result = create_survey_item(mock_db, data)

        assert result.id == str(oid)
        assert result.prompt == "How motivated are you?"
        assert result.type == "likert"
        assert result.scale is not None
        assert result.options is None

        mock_col.insert_one.assert_called_once()
        inserted_doc = mock_col.insert_one.call_args[0][0]
        assert "created_at" in inserted_doc
        assert "updated_at" in inserted_doc

    def test_creates_single_select_item(self, mock_db, mock_col):
        oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=oid)

        data = SurveyItemCreate(
            stage="pre_quiz",
            prompt="What is your favorite color?",
            type="single_select",
            options=[{"id": "red", "label": "Red"}, {"id": "blue", "label": "Blue"}],
        )
        result = create_survey_item(mock_db, data)

        assert result.id == str(oid)
        assert result.type == "single_select"
        assert result.scale is None
        assert len(result.options) == 2

    def test_ensures_indexes_before_insert(self, mock_db, mock_col):
        mock_col.insert_one.return_value = MagicMock(inserted_id=ObjectId())

        data = SurveyItemCreate(stage="pre_quiz", prompt="p")
        create_survey_item(mock_db, data)

        # ensure_survey_indexes calls create_index twice
        assert mock_col.create_index.call_count == 2


# ── list_survey_items ────────────────────────────────────────────────────────

class TestListSurveyItems:
    def test_returns_all_items_when_no_filters(self, mock_db, mock_col):
        oid1, oid2 = ObjectId(), ObjectId()
        mock_col.find.return_value.sort.return_value = [
            {
                "_id": oid1, "stage": "pre_quiz", "prompt": "Q1", "type": "likert",
                "required": True, "order": 0, "active": True, "category": None,
                "reverse_scored": False,
                "scale": {"min": 1, "max": 5, "anchors": None}, "options": None,
            },
            {
                "_id": oid2, "stage": "pre_quiz", "prompt": "Q2", "type": "likert",
                "required": True, "order": 1, "active": True, "category": None,
                "reverse_scored": False,
                "scale": {"min": 1, "max": 5, "anchors": None}, "options": None,
            },
        ]

        items = list_survey_items(mock_db)

        assert len(items) == 2
        assert items[0].id == str(oid1)
        assert items[1].id == str(oid2)
        mock_col.find.assert_called_with({})

    def test_filters_by_stage(self, mock_db, mock_col):
        mock_col.find.return_value.sort.return_value = []

        list_survey_items(mock_db, stage="post_base")

        mock_col.find.assert_called_with({"stage": "post_base"})

    def test_filters_by_active_only(self, mock_db, mock_col):
        mock_col.find.return_value.sort.return_value = []

        list_survey_items(mock_db, active_only=True)

        mock_col.find.assert_called_with({"active": True})

    def test_filters_by_stage_and_active(self, mock_db, mock_col):
        mock_col.find.return_value.sort.return_value = []

        list_survey_items(mock_db, stage="pre_quiz", active_only=True)

        mock_col.find.assert_called_with({"stage": "pre_quiz", "active": True})

    def test_empty_result_returns_empty_list(self, mock_db, mock_col):
        mock_col.find.return_value.sort.return_value = []
        assert list_survey_items(mock_db) == []

    def test_results_sorted_by_order(self, mock_db, mock_col):
        mock_col.find.return_value.sort.return_value = []
        list_survey_items(mock_db)
        mock_col.find.return_value.sort.assert_called_with("order", 1)


# ── update_survey_item ───────────────────────────────────────────────────────

class TestUpdateSurveyItem:
    def test_updates_existing_item(self, mock_db, mock_col):
        oid = ObjectId()
        existing = {
            "_id": oid, "stage": "pre_quiz", "prompt": "Old prompt", "type": "likert",
            "required": True, "order": 0, "active": True, "category": None,
            "reverse_scored": False,
            "scale": {"min": 1, "max": 5, "anchors": None}, "options": None,
        }
        updated = dict(existing)
        updated["prompt"] = "New prompt"

        mock_col.find_one.side_effect = [existing, updated]

        patch = SurveyItemUpdate(prompt="New prompt")
        result = update_survey_item(mock_db, str(oid), patch)

        assert result.prompt == "New prompt"
        mock_col.update_one.assert_called_once()
        call_args = mock_col.update_one.call_args
        assert call_args[0][0] == {"_id": oid}
        set_doc = call_args[0][1]["$set"]
        assert "_id" not in set_doc
        assert set_doc["prompt"] == "New prompt"

    def test_not_found_raises_404(self, mock_db, mock_col):
        mock_col.find_one.return_value = None

        patch = SurveyItemUpdate(prompt="New prompt")
        with pytest.raises(HTTPException) as exc_info:
            update_survey_item(mock_db, str(ObjectId()), patch)

        assert exc_info.value.status_code == 404

    def test_switching_to_single_select_requires_options(self, mock_db, mock_col):
        oid = ObjectId()
        existing = {
            "_id": oid, "stage": "pre_quiz", "prompt": "p", "type": "likert",
            "required": True, "order": 0, "active": True, "category": None,
            "reverse_scored": False,
            "scale": {"min": 1, "max": 5, "anchors": None}, "options": None,
        }
        mock_col.find_one.return_value = existing

        # Switching type to single_select without providing options should fail
        patch = SurveyItemUpdate(type="single_select")
        with pytest.raises(HTTPException) as exc_info:
            update_survey_item(mock_db, str(oid), patch)

        assert exc_info.value.status_code == 400

    def test_switching_to_single_select_with_options_succeeds(self, mock_db, mock_col):
        oid = ObjectId()
        existing = {
            "_id": oid, "stage": "pre_quiz", "prompt": "p", "type": "likert",
            "required": True, "order": 0, "active": True, "category": None,
            "reverse_scored": False,
            "scale": {"min": 1, "max": 5, "anchors": None}, "options": None,
        }
        updated = dict(existing)
        updated["type"] = "single_select"
        updated["scale"] = None
        updated["options"] = [{"id": "a", "label": "Yes"}, {"id": "b", "label": "No"}]

        mock_col.find_one.side_effect = [existing, updated]

        patch = SurveyItemUpdate(
            type="single_select",
            options=[{"id": "a", "label": "Yes"}, {"id": "b", "label": "No"}],
        )
        result = update_survey_item(mock_db, str(oid), patch)

        assert result.type == "single_select"
        assert result.scale is None
        assert len(result.options) == 2

    def test_partial_patch_only_sets_provided_fields(self, mock_db, mock_col):
        oid = ObjectId()
        existing = {
            "_id": oid, "stage": "pre_quiz", "prompt": "Old", "type": "likert",
            "required": True, "order": 0, "active": True, "category": "wellbeing",
            "reverse_scored": False,
            "scale": {"min": 1, "max": 5, "anchors": None}, "options": None,
        }
        updated = dict(existing)
        updated["active"] = False

        mock_col.find_one.side_effect = [existing, updated]

        patch = SurveyItemUpdate(active=False)
        result = update_survey_item(mock_db, str(oid), patch)

        assert result.active is False
        assert result.category == "wellbeing"
        assert result.prompt == "Old"


# ── delete_survey_item ───────────────────────────────────────────────────────

class TestDeleteSurveyItem:
    def test_deletes_existing_item(self, mock_db, mock_col):
        mock_col.delete_one.return_value = MagicMock(deleted_count=1)

        # should not raise
        delete_survey_item(mock_db, str(ObjectId()))

        mock_col.delete_one.assert_called_once()

    def test_not_found_raises_404(self, mock_db, mock_col):
        mock_col.delete_one.return_value = MagicMock(deleted_count=0)

        with pytest.raises(HTTPException) as exc_info:
            delete_survey_item(mock_db, str(ObjectId()))

        assert exc_info.value.status_code == 404



# Stateful survey behavior uses an in-memory database so snapshots and conditional
# writes are exercised instead of asserting an implementation's call sequence.
@pytest.fixture
def survey_store():
    import mongomock
    from tests.conftest import standard_step_order
    db = mongomock.MongoClient().db
    uid = db.users.insert_one({"email": "student@example.com", "step_order": standard_step_order(), "completed_steps": [], "quiz_set_assignment": {}}).inserted_id
    return db, str(uid), "student@example.com"


def _add_state_item(db, stage="pre_quiz", **kwargs):
    return create_survey_item(db, SurveyItemCreate(stage=stage, prompt="Question", **kwargs))

# ── build_survey_state ───────────────────────────────────────────────────────

class TestBuildSurveyState:
    def test_invalid_stage_raises_400(self, survey_store):
        db, uid, email = survey_store
        with pytest.raises(HTTPException) as error:
            build_survey_state(db, uid, email, "not_real")
        assert error.value.status_code == 400

    def test_creates_new_response_doc_when_none_exists(self, survey_store):
        db, uid, email = survey_store
        state = build_survey_state(db, uid, email, "pre_quiz")
        assert state.attempt.status == "in_progress" and state.attempt.total_items == 0
        assert db.survey_responses.count_documents({"user_id": uid, "stage": "pre_quiz"}) == 1
        assert db.survey_responses.find_one({})["item_snapshot"] == []

    def test_returns_existing_response_doc_with_items_and_answers(self, survey_store):
        db, uid, email = survey_store
        item = _add_state_item(db)
        build_survey_state(db, uid, email, "pre_quiz")
        db.survey_responses.update_one({"user_id": uid}, {"$set": {"answers": [{"item_id": item.id, "value": 4, "answered_at": datetime.now(timezone.utc)}]}})
        state = build_survey_state(db, uid, email, "pre_quiz")
        assert state.attempt.answered_count == 1 and state.attempt.total_items == 1
        assert state.answers[0].value == 4 and state.items[0].id == item.id

    def test_post_variant_uses_post_base_items(self, survey_store):
        db, uid, email = survey_store
        item = _add_state_item(db, "post_base")
        assert build_survey_state(db, uid, email, "post_variant").items[0].id == item.id

    def test_unanswered_items_not_counted_in_answered_count(self, survey_store):
        db, uid, email = survey_store
        item = _add_state_item(db)
        db.survey_responses.insert_one({"user_id": uid, "stage": "pre_quiz", "status": "in_progress", "answers": [{"item_id": item.id, "answered_at": None}]})
        assert build_survey_state(db, uid, email, "pre_quiz").attempt.answered_count == 0



# ── build_survey_state: per-participant randomization ─────────────────────────

def _likert_item_doc(oid: ObjectId, order: int) -> dict:
    return {
        "_id": oid, "stage": "pre_quiz", "prompt": f"Q{order}", "type": "likert",
        "required": True, "order": order, "active": True, "category": None,
        "reverse_scored": False,
        "scale": {"min": 1, "max": 5, "anchors": None}, "options": None,
    }


class TestBuildSurveyStateRandomization:
    def test_preserves_the_full_item_set(self, survey_store):
        db, uid, email = survey_store
        ids = {_add_state_item(db).id for _ in range(10)}
        assert {i.id for i in build_survey_state(db, uid, email, "pre_quiz").items} == ids

    def test_order_is_deterministic_for_same_user_and_stage(self, survey_store):
        db, uid, email = survey_store
        for _ in range(10): _add_state_item(db)
        first = build_survey_state(db, uid, email, "pre_quiz")
        assert [i.id for i in first.items] == [i.id for i in build_survey_state(db, uid, email, "pre_quiz").items]

    def test_order_varies_across_users_and_stages(self, survey_store):
        db, uid, email = survey_store
        for _ in range(10): _add_state_item(db, scope="all_surveys")
        orders = {tuple(i.id for i in build_survey_state(db, user, email, stage).items) for user in (uid, str(ObjectId())) for stage in ("pre_quiz", "post_base")}
        assert len(orders) > 1



# ── record_item_shown ────────────────────────────────────────────────────────

class TestRecordItemShown:
    def test_pushes_shown_entry_for_new_item(self, mock_db, mock_col):
        record_item_shown(mock_db, "user1", "pre_quiz", "item123")

        mock_col.update_one.assert_called_once()
        call_args = mock_col.update_one.call_args
        query = call_args[0][0]
        update = call_args[0][1]

        assert query == {
            "user_id": "user1",
            "stage": "pre_quiz",
            "answers.item_id": {"$ne": "item123"},
        }
        pushed = update["$push"]["answers"]
        assert pushed["item_id"] == "item123"
        assert pushed["answered_at"] is None
        assert pushed["value"] is None
        assert "shown_at" in pushed
        assert "updated_at" in update["$set"]

    def test_returns_none(self, mock_db, mock_col):
        result = record_item_shown(mock_db, "user1", "pre_quiz", "item123")
        assert result is None


# ── submit_survey ─────────────────────────────────────────────────────────────

class TestSubmitSurvey:
    def test_already_completed_returns_original_state_without_rewriting_answers(self, survey_store):
        db, uid, email = survey_store
        item = _add_state_item(db)
        req = SurveySubmitRequest(answers=[SurveyAnswerIn(item_id=item.id, value=4)])
        submit_survey(db, uid, email, "pre_quiz", req)
        original = db.survey_responses.find_one({})
        result = submit_survey(db, uid, email, "pre_quiz", SurveySubmitRequest(answers=[SurveyAnswerIn(item_id=item.id, value=1)]))
        assert result.attempt.status == "completed"
        assert db.survey_responses.find_one({})["answers"] == original["answers"]

    def test_invalid_stage_raises_400(self, survey_store):
        db, uid, email = survey_store
        with pytest.raises(HTTPException) as error: submit_survey(db, uid, email, "bogus", SurveySubmitRequest(answers=[]))
        assert error.value.status_code == 400
        assert db.survey_responses.count_documents({}) == 0

    def test_invalid_item_id_raises_400(self, survey_store):
        db, uid, email = survey_store
        with pytest.raises(HTTPException) as error: submit_survey(db, uid, email, "pre_quiz", SurveySubmitRequest(answers=[SurveyAnswerIn(item_id="invalid", value=4)]))
        assert error.value.status_code == 400

    def test_partial_completion_does_not_set_completed(self, survey_store):
        db, uid, email = survey_store
        one, two = _add_state_item(db), _add_state_item(db)
        state = submit_survey(db, uid, email, "pre_quiz", SurveySubmitRequest(answers=[SurveyAnswerIn(item_id=one.id, value=4)]))
        assert state.attempt.status == "in_progress"
        assert "survey:pre_quiz" not in db.users.find_one({})["completed_steps"]

    @pytest.mark.parametrize("stage", ["pre_quiz", "post_base", "post_followup"])
    def test_full_completion_sets_flags_and_payload(self, survey_store, stage):
        db, uid, email = survey_store
        question_stage = "pre_quiz" if stage == "pre_quiz" else "post_base"
        item = _add_state_item(db, question_stage)
        state = submit_survey(db, uid, email, stage, SurveySubmitRequest(answers=[SurveyAnswerIn(item_id=item.id, value=5)]))
        assert state.attempt.status == "completed"
        assert db.users.find_one({})[f"{stage}_survey"] == {item.id: 5}
        assert f"survey:{stage}" in db.users.find_one({})["completed_steps"]

    def test_full_completion_of_last_step_sets_complete_stage(self, survey_store):
        db, uid, email = survey_store
        order = db.users.find_one({})["step_order"]
        stage = order[-1].split(":")[1]
        db.users.update_one({}, {"$set": {"completed_steps": order[:-1]}})
        item = _add_state_item(db, "post_base")
        submit_survey(db, uid, email, stage, SurveySubmitRequest(answers=[SurveyAnswerIn(item_id=item.id, value=4)]))
        assert db.users.find_one({})["survey_stage"] == "complete"

    def test_user_not_found_raises_404(self, survey_store):
        db, uid, email = survey_store
        db.users.delete_many({})
        with pytest.raises(HTTPException) as error: submit_survey(db, uid, email, "pre_quiz", SurveySubmitRequest(answers=[]))
        assert error.value.status_code == 404

    def test_new_answer_is_pushed_and_existing_answer_can_change_before_completion(self, survey_store):
        db, uid, email = survey_store
        one, two = _add_state_item(db), _add_state_item(db)
        for value in (2, 4): submit_survey(db, uid, email, "pre_quiz", SurveySubmitRequest(answers=[SurveyAnswerIn(item_id=one.id, value=value)]))
        answers = db.survey_responses.find_one({})["answers"]
        assert len(answers) == 1 and answers[0]["value"] == 4
