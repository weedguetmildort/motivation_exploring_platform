# backend/tests/test_study_preview.py
"""Admin previews must draw question sets the way participants do, without
claiming participants' balanced-random slots."""
from unittest.mock import MagicMock

import mongomock
import pytest
from bson import ObjectId

from app.schemas.question import ALL_SET_IDS
from app.services import study_flow as sf
from app.services.study_preview import admin_preview_fields, preview_quiz_sets, refresh_admin_preview
from app.services.study_repair import repair_study1_flow
from app.services.studies import StudyDatabase, initialize_studies

ORDER = sf.build_step_order(["followup", "double", "links"])
QUIZZES = sf.quiz_ids_in_order(ORDER)


def config(**overrides):
    return sf.StudyConfig(variant_order=tuple(sf.all_variants()), **overrides)


class TestPreviewQuizSets:
    def test_preset_follows_the_current_map_only(self):
        preset = config(quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map=(("base", "b"),))
        stored = {"base": "a", "followup": "c"}  # e.g. the old hard-coded a/b/c/d preview
        assert preview_quiz_sets(preset, ORDER, stored) == {"base": "b"}

    def test_preset_with_an_empty_map_draws_from_the_whole_pool(self):
        assert preview_quiz_sets(config(quiz_set_mode=sf.QUIZ_SET_MODE_PRESET), ORDER, {"base": "a"}) == {}

    @pytest.mark.parametrize("mode", [sf.QUIZ_SET_MODE_RANDOM, sf.QUIZ_SET_MODE_BALANCED_RANDOM])
    def test_random_modes_give_every_quiz_a_distinct_set(self, mode):
        sets = preview_quiz_sets(config(quiz_set_mode=mode), ORDER, None)
        assert sorted(sets) == sorted(QUIZZES[:len(ALL_SET_IDS)])
        assert len(set(sets.values())) == len(sets) and set(sets.values()) <= set(ALL_SET_IDS)

    def test_random_modes_keep_an_existing_distinct_assignment(self):
        stored = dict(zip(QUIZZES, reversed(ALL_SET_IDS)))
        assert preview_quiz_sets(config(), ORDER, stored) == stored

    def test_random_modes_redraw_an_assignment_with_a_repeated_set(self):
        stored = {quiz: ALL_SET_IDS[0] for quiz in QUIZZES}
        sets = preview_quiz_sets(config(), ORDER, stored)
        assert len(set(sets.values())) == len(QUIZZES)

    def test_random_modes_redraw_when_the_order_gains_a_quiz(self):
        stored = {"base": ALL_SET_IDS[0]}
        assert sorted(preview_quiz_sets(config(), ORDER, stored)) == sorted(QUIZZES)

    def test_entries_for_quizzes_no_longer_in_the_order_are_dropped(self):
        stored = {**dict(zip(QUIZZES, ALL_SET_IDS)), "retired": "a"}
        assert "retired" not in preview_quiz_sets(config(), ORDER, stored)


class TestAdminPreviewFields:
    @pytest.fixture
    def raw(self):
        raw = mongomock.MongoClient().db
        initialize_studies(raw)
        return raw

    def test_study2_preview_records_the_access_policy(self, raw, monkeypatch):
        from app.core.config import get_settings
        monkeypatch.setattr(get_settings(), "STUDY_ACCESS_MODE", "sequential")
        protocol = admin_preview_fields(StudyDatabase(raw, "study-2"), {})["study_protocol"]
        assert protocol["requires_study1_completion"] is True
        assert protocol["requires_study2_approval"] is False
        assert protocol["study_access_mode"] == "sequential"

    def test_study1_preview_does_not_claim_study2_access_rules(self, raw):
        protocol = admin_preview_fields(StudyDatabase(raw, "study-1"), {})["study_protocol"]
        assert "study_access_mode" not in protocol

    def test_refresh_writes_only_when_something_changed(self, raw):
        db = StudyDatabase(raw, "study-2")
        admin = raw.users.insert_one({"email": "a@example.com", "is_admin": True}).inserted_id
        raw.study_enrollments.insert_one({"_id": admin})
        first = refresh_admin_preview(db, db["users"].find_one({"_id": admin}))
        stored = raw.study_enrollments.find_one({"_id": admin})
        assert stored["quiz_set_assignment"] == first["quiz_set_assignment"]
        users = MagicMock(wraps=db["users"])
        class Probe:
            study_id = "study-2"
            def __getitem__(self, name):
                return users if name == "users" else db[name]
        refresh_admin_preview(Probe(), db["users"].find_one({"_id": admin}))
        users.update_one.assert_not_called()


class TestRepairLookup:
    def _db(self):
        db = MagicMock()
        db.study_id = "study-1"
        return db

    def test_an_ordinary_single_variant_journey_skips_the_audit_lookup(self):
        db = self._db()
        doc = {"_id": ObjectId(), "step_order": ["survey:pre_quiz", "quiz:base", "quiz:links"]}
        assert repair_study1_flow(db, doc) is doc
        db.__getitem__.assert_not_called()

    def test_a_legacy_account_without_a_journey_skips_the_audit_lookup(self):
        db = self._db()
        doc = {"_id": ObjectId()}
        assert repair_study1_flow(db, doc) is doc
        db.__getitem__.assert_not_called()

    def test_a_repaired_account_still_checks_for_an_unfinished_audit(self):
        db = self._db()
        db["study_flow_repairs"].find_one.return_value = {"finished_at": "done"}
        db.__getitem__.reset_mock()
        doc = {"_id": ObjectId(), "step_order": ["quiz:links"], "study1_repair_version": 1}
        assert repair_study1_flow(db, doc) is doc
        db.__getitem__.assert_called_with("study_flow_repairs")

    def test_an_unfinished_repair_is_completed(self):
        raw = mongomock.MongoClient().db
        db = StudyDatabase(raw, "study-1")
        uid = raw.users.insert_one({"email": "p@example.com", "assigned_var": "links",
                                    "step_order": ["survey:pre_quiz", "quiz:base", "quiz:links", "survey:post_variant"],
                                    "completed_steps": [], "study1_repair_version": 1}).inserted_id
        raw.study_flow_repairs.insert_one({"_id": str(uid), "retained_variant": "links"})
        repair_study1_flow(db, db["users"].find_one({"_id": uid}))
        assert raw.study_flow_repairs.find_one({"_id": str(uid)})["finished_at"]

    def test_a_journey_with_several_variants_is_still_repaired(self):
        raw = mongomock.MongoClient().db
        db = StudyDatabase(raw, "study-1")
        uid = raw.users.insert_one({"email": "p@example.com", "assigned_var": "links", "completed_steps": [],
                                    "step_order": ["survey:pre_quiz", "quiz:base", "quiz:links", "quiz:double"]}).inserted_id
        repaired = repair_study1_flow(db, db["users"].find_one({"_id": uid}))
        assert [s for s in repaired["step_order"] if s.startswith("quiz:")] == ["quiz:base", "quiz:links"]
