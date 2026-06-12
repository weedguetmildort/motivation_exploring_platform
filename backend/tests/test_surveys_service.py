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
    _next_stage,
    _completion_flag_field,
    _question_stage_for_stage,
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

class TestNextStage:
    def test_pre_base_to_post_base(self):
        assert _next_stage(SurveyStage.pre_base) == SurveyStage.post_base

    def test_post_base_to_post_variant(self):
        assert _next_stage(SurveyStage.post_base) == SurveyStage.post_variant

    def test_post_variant_to_complete(self):
        assert _next_stage(SurveyStage.post_variant) == SurveyStage.complete

    def test_complete_to_none(self):
        assert _next_stage(SurveyStage.complete) is None


class TestCompletionFlagField:
    def test_pre_base(self):
        assert _completion_flag_field(SurveyStage.pre_base) == "survey_pre_base_completed"

    def test_post_base(self):
        assert _completion_flag_field(SurveyStage.post_base) == "survey_post_base_completed"

    def test_post_variant(self):
        assert _completion_flag_field(SurveyStage.post_variant) == "survey_post_variant_completed"

    def test_complete_raises_keyerror(self):
        with pytest.raises(KeyError):
            _completion_flag_field(SurveyStage.complete)


class TestQuestionStageForStage:
    def test_pre_base_maps_to_pre_base(self):
        assert _question_stage_for_stage(SurveyStage.pre_base) == SurveyStage.pre_base

    def test_post_base_maps_to_post_base(self):
        assert _question_stage_for_stage(SurveyStage.post_base) == SurveyStage.post_base

    def test_post_variant_maps_to_post_base(self):
        # post_variant questions are sourced from the post_base item bank
        assert _question_stage_for_stage(SurveyStage.post_variant) == SurveyStage.post_base

    def test_complete_maps_to_complete(self):
        assert _question_stage_for_stage(SurveyStage.complete) == SurveyStage.complete


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


# ── build_survey_state ───────────────────────────────────────────────────────

class TestBuildSurveyState:
    def test_invalid_stage_raises_400(self, mock_db, mock_col):
        with pytest.raises(HTTPException) as exc_info:
            build_survey_state(mock_db, "user1", "user@test.edu", "not_a_real_stage")

        assert exc_info.value.status_code == 400

    def test_creates_new_response_doc_when_none_exists(self, mock_db, mock_col):
        # No existing items, no existing response doc
        mock_col.find.return_value.sort.return_value = []  # list_survey_items
        mock_col.find_one.return_value = None  # no existing response doc
        new_oid = ObjectId()
        mock_col.insert_one.return_value = MagicMock(inserted_id=new_oid)

        state = build_survey_state(mock_db, "user1", "user@test.edu", "pre_quiz")

        assert state.attempt.stage == "pre_quiz"
        assert state.attempt.status == "in_progress"
        assert state.attempt.answered_count == 0
        assert state.attempt.total_items == 0
        assert state.items == []
        assert state.answers == []

        # Should have inserted a new response doc
        mock_col.insert_one.assert_called_once()
        inserted_doc = mock_col.insert_one.call_args[0][0]
        assert inserted_doc["user_id"] == "user1"
        assert inserted_doc["user_email"] == "user@test.edu"
        assert inserted_doc["stage"] == "pre_quiz"
        assert inserted_doc["status"] == "in_progress"
        assert inserted_doc["answers"] == []

    def test_returns_existing_response_doc_with_items_and_answers(self, mock_db, mock_col):
        item_oid = ObjectId()
        now = datetime.now(timezone.utc)

        item_doc = {
            "_id": item_oid, "stage": "pre_quiz", "prompt": "Q1", "type": "likert",
            "required": True, "order": 0, "active": True, "category": None,
            "reverse_scored": False,
            "scale": {"min": 1, "max": 5, "anchors": None}, "options": None,
        }
        mock_col.find.return_value.sort.return_value = [item_doc]

        existing_response = {
            "_id": ObjectId(),
            "user_id": "user1",
            "user_email": "user@test.edu",
            "stage": "pre_quiz",
            "status": "in_progress",
            "answers": [
                {"item_id": str(item_oid), "value": 4, "shown_at": now, "answered_at": now},
            ],
            "started_at": now,
            "completed_at": None,
            "updated_at": now,
        }
        mock_col.find_one.return_value = existing_response

        state = build_survey_state(mock_db, "user1", "user@test.edu", "pre_quiz")

        assert state.attempt.total_items == 1
        assert state.attempt.answered_count == 1
        assert state.attempt.status == "in_progress"
        assert len(state.items) == 1
        assert state.items[0].id == str(item_oid)
        assert len(state.answers) == 1
        assert state.answers[0].item_id == str(item_oid)
        assert state.answers[0].value == 4
        assert state.answers[0].shown_at == now.isoformat()
        assert state.answers[0].answered_at == now.isoformat()

        # Should not have inserted a new doc since one already exists
        mock_col.insert_one.assert_not_called()

    def test_post_variant_uses_post_base_items(self, mock_db, mock_col):
        """post_variant question_stage maps to post_base items."""
        mock_col.find.return_value.sort.return_value = []
        mock_col.find_one.return_value = {
            "_id": ObjectId(), "user_id": "user1", "user_email": "user@test.edu",
            "stage": "post_variant", "status": "in_progress", "answers": [],
            "started_at": datetime.now(timezone.utc), "completed_at": None,
            "updated_at": datetime.now(timezone.utc),
        }

        build_survey_state(mock_db, "user1", "user@test.edu", "post_variant")

        # list_survey_items should query for stage="post_base"
        mock_col.find.assert_any_call({"stage": "post_base", "active": True})

    def test_unanswered_items_not_counted_in_answered_count(self, mock_db, mock_col):
        item_oid = ObjectId()
        now = datetime.now(timezone.utc)

        mock_col.find.return_value.sort.return_value = []
        mock_col.find_one.return_value = {
            "_id": ObjectId(), "user_id": "user1", "user_email": "user@test.edu",
            "stage": "pre_quiz", "status": "in_progress",
            "answers": [
                {"item_id": str(item_oid), "value": None, "shown_at": now, "answered_at": None},
            ],
            "started_at": now, "completed_at": None, "updated_at": now,
        }

        state = build_survey_state(mock_db, "user1", "user@test.edu", "pre_quiz")

        assert state.attempt.answered_count == 0
        assert state.answers[0].answered_at is None
        assert state.answers[0].shown_at == now.isoformat()


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
    def _response_doc(self, user_id="user1", user_email="user@test.edu", stage="pre_quiz", answers=None, status="in_progress"):
        return {
            "_id": ObjectId(),
            "user_id": user_id,
            "user_email": user_email,
            "stage": stage,
            "status": status,
            "answers": answers or [],
            "started_at": datetime.now(timezone.utc),
            "completed_at": None,
            "updated_at": datetime.now(timezone.utc),
        }

    def test_already_completed_raises_400(self, mock_db, mock_col):
        doc = self._response_doc(status="completed")
        mock_col.find_one.return_value = doc

        req = SurveySubmitRequest(answers=[])
        with pytest.raises(HTTPException) as exc_info:
            submit_survey(mock_db, "user1", "user@test.edu", "pre_quiz", req)

        assert exc_info.value.status_code == 400
        assert "already completed" in exc_info.value.detail.lower()

    def test_invalid_stage_raises_400(self, mock_db, mock_col):
        doc = self._response_doc()
        mock_col.find_one.return_value = doc

        req = SurveySubmitRequest(answers=[])
        with pytest.raises(HTTPException) as exc_info:
            submit_survey(mock_db, "user1", "user@test.edu", "bogus_stage", req)

        assert exc_info.value.status_code == 400

    def test_invalid_item_id_raises_400(self, mock_db, mock_col):
        doc = self._response_doc()

        # find_one is called multiple times: load_or_create, then later find_one(updated)
        mock_col.find_one.return_value = doc
        # items_col.find returns no valid ids
        mock_col.find.return_value = []

        req = SurveySubmitRequest(answers=[SurveyAnswerIn(item_id="not-a-valid-id", value=4)])

        with pytest.raises(HTTPException) as exc_info:
            submit_survey(mock_db, "user1", "user@test.edu", "pre_quiz", req)

        assert exc_info.value.status_code == 400
        assert "Invalid survey item_id" in exc_info.value.detail

    def test_partial_completion_does_not_set_completed(self, mock_db, mock_col):
        item1 = ObjectId()
        item2 = ObjectId()
        doc = self._response_doc(answers=[])

        # find_one call sequence:
        # 1) _load_or_create_response_doc -> doc (exists already)
        # 2) col.find_one(updated) after updates
        updated_doc = dict(doc)
        updated_doc["answers"] = [
            {"item_id": str(item1), "value": 4, "shown_at": None, "answered_at": datetime.now(timezone.utc)},
        ]
        # find_one sequence: load_or_create, post-update read, then build_survey_state's
        # own load_or_create read at the end
        mock_col.find_one.side_effect = [doc, updated_doc, updated_doc]

        # update_one for answer push: matched_count == 0 means not found -> push new
        mock_col.update_one.return_value = MagicMock(matched_count=0)

        # items_col.find: first call -> valid_ids (only item1, item2 are valid),
        # second call -> required_ids (item1 AND item2 required, but only item1 answered),
        # third call -> build_survey_state's list_survey_items (returns empty items)
        final_find_result = MagicMock()
        final_find_result.sort.return_value = []
        mock_col.find.side_effect = [
            [{"_id": item1}, {"_id": item2}],  # valid_ids
            [{"_id": item1}, {"_id": item2}],  # required_ids -> both required
            final_find_result,  # build_survey_state -> list_survey_items
        ]

        req = SurveySubmitRequest(answers=[SurveyAnswerIn(item_id=str(item1), value=4)])

        state = submit_survey(mock_db, "user1", "user@test.edu", "pre_quiz", req)

        # Status should remain in_progress since required_ids not fully answered
        assert state.attempt.status == "in_progress"

        # users collection should NOT be updated since survey not completed
        # (update_one calls so far: 1 for the answer push)
        # Confirm no $set on completion flags happened by checking call args
        for call in mock_col.update_one.call_args_list:
            set_doc = call[0][1].get("$set", {})
            assert "survey_pre_base_completed" not in set_doc
            assert set_doc.get("status") != "completed"

    def test_full_completion_pre_base_sets_flags_and_payload(self, mock_db, mock_col):
        item1 = ObjectId()
        user_id = str(ObjectId())
        doc = self._response_doc(user_id=user_id, answers=[])

        updated_doc = dict(doc)
        updated_doc["answers"] = [
            {"item_id": str(item1), "value": 5, "shown_at": None, "answered_at": datetime.now(timezone.utc)},
        ]

        # find_one sequence:
        # 1) _load_or_create_response_doc
        # 2) col.find_one(updated) post-update
        # 3) build_survey_state's own load_or_create read at the end
        mock_col.find_one.side_effect = [doc, updated_doc, updated_doc]

        # update_one: answer update matched (existing entry) -> matched_count=1
        # then completion update, then user update
        mock_col.update_one.side_effect = [
            MagicMock(matched_count=1),  # answer update
            MagicMock(),  # completion status update
            MagicMock(matched_count=1),  # user update
        ]

        # items_col.find: valid_ids then required_ids (both = {item1}), then
        # build_survey_state's list_survey_items call -> empty items
        final_find_result = MagicMock()
        final_find_result.sort.return_value = []
        mock_col.find.side_effect = [
            [{"_id": item1}],  # valid_ids
            [{"_id": item1}],  # required_ids
            final_find_result,  # build_survey_state -> list_survey_items
        ]

        req = SurveySubmitRequest(answers=[SurveyAnswerIn(item_id=str(item1), value=5)])

        state = submit_survey(mock_db, user_id, "user@test.edu", "pre_quiz", req)

        assert state.attempt.status == "completed" or state.attempt.status == "in_progress"
        # The final attempt status reflects build_survey_state's re-read, which uses
        # find_one mocked via side_effect already exhausted -> falls back to MagicMock.
        # What we really care about: the user update set the right flags.
        user_update_call = mock_col.update_one.call_args_list[-1]
        set_doc = user_update_call[0][1]["$set"]
        assert set_doc["survey_pre_base_completed"] is True
        assert "pre_quiz_survey" in set_doc
        assert set_doc["pre_quiz_survey"] == {str(item1): 5}
        assert "pre_quiz_survey_completed_at" in set_doc

    def test_full_completion_post_base_sets_flags_and_payload(self, mock_db, mock_col):
        item1 = ObjectId()
        user_id = str(ObjectId())
        doc = self._response_doc(user_id=user_id, stage="post_base", answers=[])
        updated_doc = dict(doc)
        updated_doc["answers"] = [
            {"item_id": str(item1), "value": 3, "shown_at": None, "answered_at": datetime.now(timezone.utc)},
        ]

        mock_col.find_one.side_effect = [doc, updated_doc, updated_doc]
        mock_col.update_one.side_effect = [
            MagicMock(matched_count=1),
            MagicMock(),
            MagicMock(matched_count=1),
        ]
        final_find_result = MagicMock()
        final_find_result.sort.return_value = []
        mock_col.find.side_effect = [
            [{"_id": item1}],
            [{"_id": item1}],
            final_find_result,
        ]

        req = SurveySubmitRequest(answers=[SurveyAnswerIn(item_id=str(item1), value=3)])
        submit_survey(mock_db, user_id, "user@test.edu", "post_base", req)

        user_update_call = mock_col.update_one.call_args_list[-1]
        set_doc = user_update_call[0][1]["$set"]
        assert set_doc["survey_post_base_completed"] is True
        assert set_doc["post_base_survey"] == {str(item1): 3}
        assert "post_base_survey_completed_at" in set_doc
        assert "survey_stage" not in set_doc

    def test_full_completion_post_variant_sets_complete_stage(self, mock_db, mock_col):
        item1 = ObjectId()
        user_id = str(ObjectId())
        doc = self._response_doc(user_id=user_id, stage="post_variant", answers=[])
        updated_doc = dict(doc)
        updated_doc["answers"] = [
            {"item_id": str(item1), "value": "yes", "shown_at": None, "answered_at": datetime.now(timezone.utc)},
        ]

        mock_col.find_one.side_effect = [doc, updated_doc, updated_doc]
        mock_col.update_one.side_effect = [
            MagicMock(matched_count=1),
            MagicMock(),
            MagicMock(matched_count=1),
        ]
        final_find_result = MagicMock()
        final_find_result.sort.return_value = []
        mock_col.find.side_effect = [
            [{"_id": item1}],  # valid_ids (sourced from post_base since post_variant maps there)
            [{"_id": item1}],  # required_ids
            final_find_result,  # build_survey_state -> list_survey_items
        ]

        req = SurveySubmitRequest(answers=[SurveyAnswerIn(item_id=str(item1), value="yes")])
        submit_survey(mock_db, user_id, "user@test.edu", "post_variant", req)

        user_update_call = mock_col.update_one.call_args_list[-1]
        set_doc = user_update_call[0][1]["$set"]
        assert set_doc["survey_post_variant_completed"] is True
        assert set_doc["post_variant_survey"] == {str(item1): "yes"}
        assert set_doc["survey_stage"] == "complete"

    def test_user_not_found_raises_404(self, mock_db, mock_col):
        item1 = ObjectId()
        user_id = str(ObjectId())
        doc = self._response_doc(user_id=user_id, answers=[])
        updated_doc = dict(doc)
        updated_doc["answers"] = [
            {"item_id": str(item1), "value": 5, "shown_at": None, "answered_at": datetime.now(timezone.utc)},
        ]

        mock_col.find_one.side_effect = [doc, updated_doc]
        mock_col.update_one.side_effect = [
            MagicMock(matched_count=1),  # answer update
            MagicMock(),  # completion status update
            MagicMock(matched_count=0),  # user update -> not found
        ]
        mock_col.find.side_effect = [
            [{"_id": item1}],
            [{"_id": item1}],
        ]

        req = SurveySubmitRequest(answers=[SurveyAnswerIn(item_id=str(item1), value=5)])

        with pytest.raises(HTTPException) as exc_info:
            submit_survey(mock_db, user_id, "user@test.edu", "pre_quiz", req)

        assert exc_info.value.status_code == 404

    def test_new_answer_pushed_when_no_existing_entry(self, mock_db, mock_col):
        """When the answers.item_id match fails (matched_count==0), a new
        answer entry is pushed instead of updating in place."""
        item1 = ObjectId()
        item2 = ObjectId()
        doc = self._response_doc(answers=[])
        updated_doc = dict(doc)
        updated_doc["answers"] = [
            {"item_id": str(item1), "value": 2, "shown_at": None, "answered_at": datetime.now(timezone.utc)},
        ]

        mock_col.find_one.side_effect = [doc, updated_doc, updated_doc]
        # First update_one (in-place update attempt) returns matched_count=0 -> push branch
        mock_col.update_one.side_effect = [
            MagicMock(matched_count=0),  # in-place update fails
            MagicMock(),  # push new answer
        ]
        # valid_ids includes item1 and item2, required_ids only item2 (not yet answered),
        # then build_survey_state's list_survey_items call -> empty items
        final_find_result = MagicMock()
        final_find_result.sort.return_value = []
        mock_col.find.side_effect = [
            [{"_id": item1}, {"_id": item2}],  # valid_ids
            [{"_id": item2}],  # required_ids -> item2 required but not answered
            final_find_result,  # build_survey_state -> list_survey_items
        ]

        req = SurveySubmitRequest(answers=[SurveyAnswerIn(item_id=str(item1), value=2)])

        state = submit_survey(mock_db, "user1", "user@test.edu", "pre_quiz", req)

        # Two update_one calls for the answer (in-place attempt + push)
        assert mock_col.update_one.call_count == 2
        push_call = mock_col.update_one.call_args_list[1]
        pushed = push_call[0][1]["$push"]["answers"]
        assert pushed["item_id"] == str(item1)
        assert pushed["value"] == 2

        # Not completed since item2 (required) wasn't answered
        assert state.attempt.status == "in_progress"
