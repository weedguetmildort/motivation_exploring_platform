# backend/tests/test_study_flow_service.py
"""Unit tests for app/services/study_flow.py — the participant flow engine.

Uses a tiny in-memory Mongo double rather than MagicMock for the stateful paths
(assignment, progress, migration), because those read back what they just wrote.
"""
from datetime import datetime
import types

from bson import ObjectId
import pytest

from app.schemas.user import AssignedVar, SurveyStage
from app.services import study_flow as sf


# ── In-memory Mongo double ───────────────────────────────────────────────────

class FakeCol:
    def __init__(self):
        self.docs = []

    def _match(self, d, q):
        for k, v in q.items():
            if isinstance(v, dict) and "$ne" in v:
                if d.get(k) == v["$ne"]:
                    return False
            elif d.get(k) != v:
                return False
        return True

    def find_one(self, q, *a, **k):
        return next((d for d in self.docs if self._match(d, q)), None)

    def count_documents(self, q, limit=None):
        return sum(1 for d in self.docs if self._match(d, q))

    def _apply(self, d, update):
        d.update(update.get("$set", {}))
        for key, amount in update.get("$inc", {}).items():
            d[key] = d.get(key, 0) + amount

    def update_one(self, q, update, upsert=False):
        d = self.find_one(q)
        if d is None:
            if not upsert:
                return types.SimpleNamespace(matched_count=0)
            d = dict(q)
            self.docs.append(d)
        self._apply(d, update)
        return types.SimpleNamespace(matched_count=1)

    def find_one_and_update(self, q, update, upsert=False, return_document=None):
        self.update_one(q, update, upsert=upsert)
        return self.find_one(q)

    def insert_one(self, doc):
        self.docs.append(doc)
        return types.SimpleNamespace(inserted_id=doc.get("_id"))


class FakeDB:
    def __init__(self):
        self.cols = {}

    def __getitem__(self, name):
        return self.cols.setdefault(name, FakeCol())


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def config():
    return sf.StudyConfig(variant_order=tuple(sf.all_variants()))


def _signup(db, uid):
    flow = sf.assign_flow(db)
    doc = {"_id": uid, "email": f"{uid}@test.edu", "is_admin": False, **flow}
    db["users"].docs.append(doc)
    return doc


# ── Step registry ────────────────────────────────────────────────────────────

class TestStepRegistry:
    def test_every_variant_has_a_quiz_and_a_survey_step(self):
        for variant in sf.all_variants():
            assert sf.get_step(sf.quiz_step_id(variant)) is not None
            stage = sf.post_variant_stage(variant)
            assert sf.get_step(sf.survey_step_id(stage)) is not None

    def test_each_variant_survey_has_its_own_response_stage(self):
        """survey_responses is unique on (user_id, stage) — they must not collide."""
        stages = [sf.post_variant_stage(v) for v in sf.all_variants()]
        assert len(set(stages)) == len(stages)
        assert "post_base" not in stages

    def test_every_variant_survey_sources_post_base_questions(self):
        for variant in sf.all_variants():
            stage = sf.post_variant_stage(variant)
            assert sf.survey_question_stage(stage) == SurveyStage.post_base.value

    def test_legacy_post_variant_stage_stays_readable(self):
        assert sf.is_known_survey_stage(SurveyStage.post_variant.value)

    def test_quiz2_ids_are_not_part_of_the_main_flow(self):
        """Phase 13 follow-up study is a separate, admin-granted track."""
        for quiz_id in ("base2", "followup2", "links2", "double2"):
            assert not sf.is_known_quiz_id(quiz_id)

    def test_unknown_ids_are_rejected(self):
        assert sf.get_step("quiz:nope") is None
        assert not sf.is_known_survey_stage("nope")
        assert sf.survey_question_stage("nope") is None

    def test_variant_label_falls_back_for_an_unlabelled_variant(self):
        assert sf.variant_label("brand_new") == "Brand New"


# ── Counterbalancing ─────────────────────────────────────────────────────────

class TestVariantSequence:
    def test_rotation_is_a_latin_square(self, config):
        n = len(config.variant_order)
        positions = {}
        for seq in range(1, n + 1):
            for pos, variant in enumerate(sf.variant_sequence_for_seq(seq, config)):
                positions.setdefault(variant, []).append(pos)

        # Each variant lands in each position exactly once across the rotations.
        for seen in positions.values():
            assert sorted(seen) == list(range(n))

    def test_every_sequence_contains_every_variant(self, config):
        for seq in range(1, 7):
            assert sorted(sf.variant_sequence_for_seq(seq, config)) == sorted(
                config.variant_order
            )

    def test_counterbalance_off_gives_everyone_the_same_order(self, config):
        fixed = sf.StudyConfig(variant_order=config.variant_order, counterbalance=False)
        orders = [sf.variant_sequence_for_seq(s, fixed) for s in range(1, 5)]
        assert all(o == list(fixed.variant_order) for o in orders)

    def test_empty_variant_order_yields_nothing(self):
        assert sf.variant_sequence_for_seq(1, sf.StudyConfig(variant_order=())) == []


class TestBuildStepOrder:
    def test_base_quiz_always_comes_first(self, config):
        for seq in range(1, 4):
            order = sf.build_step_order(sf.variant_sequence_for_seq(seq, config))
            assert order[0] == sf.survey_step_id(SurveyStage.pre_base.value)
            assert order[1] == sf.quiz_step_id(sf.BASE_QUIZ_ID)

    def test_quizzes_and_surveys_alternate(self, config):
        order = sf.build_step_order(sf.variant_sequence_for_seq(1, config))
        kinds = [sf.get_step(s).kind for s in order]
        assert all(a != b for a, b in zip(kinds, kinds[1:]))

    def test_length_is_three_plus_two_per_variant(self, config):
        order = sf.build_step_order(config.variant_order)
        assert len(order) == 3 + 2 * len(config.variant_order)

    def test_unknown_variants_are_skipped(self):
        order = sf.build_step_order(["not_a_variant"])
        assert order == [sf.survey_step_id(SurveyStage.pre_base.value),
                         sf.quiz_step_id(sf.BASE_QUIZ_ID),
                         sf.survey_step_id(SurveyStage.post_base.value)]


# ── Config persistence ───────────────────────────────────────────────────────

class TestStudyConfig:
    def test_defaults_when_nothing_stored(self, db):
        cfg = sf.load_study_config(db)
        assert cfg.mode == sf.MODE_ALL_VARIANTS
        assert cfg.counterbalance is True
        assert list(cfg.variant_order) == sf.all_variants()

    def test_removed_variant_is_dropped_and_new_one_appended(self):
        resolved = list(sf._reconcile_variant_order(["links", "gone_variant"]))
        assert "gone_variant" not in resolved
        assert set(resolved) == set(sf.all_variants())
        # The admin's relative ordering of surviving variants is preserved.
        assert resolved[0] == "links"

    def test_duplicates_are_collapsed(self):
        resolved = list(sf._reconcile_variant_order(["links", "links"]))
        assert resolved.count("links") == 1

    def test_saving_a_change_bumps_the_version(self, db):
        before = sf.load_study_config(db).version
        after = sf.save_study_config(db, counterbalance=False)
        assert after.version == before + 1
        assert sf.load_study_config(db).counterbalance is False

    def test_saving_no_change_keeps_the_version(self, db):
        first = sf.save_study_config(db, mode=sf.MODE_ALL_VARIANTS)
        second = sf.save_study_config(db, mode=sf.MODE_ALL_VARIANTS)
        assert second.version == first.version

    def test_invalid_mode_falls_back_to_current(self, db):
        sf.save_study_config(db, mode="nonsense")
        assert sf.load_study_config(db).mode == sf.MODE_ALL_VARIANTS

    def test_stored_bad_mode_is_normalised_on_read(self, db):
        db["study_config"].docs.append({"_id": sf.STUDY_CONFIG_ID, "mode": "bogus"})
        assert sf.load_study_config(db).mode == sf.MODE_ALL_VARIANTS

    def test_as_dict_round_trips(self, config):
        assert config.as_dict()["variant_order"] == list(config.variant_order)


# ── Assignment ───────────────────────────────────────────────────────────────

class TestAssignFlow:
    def test_consecutive_signups_are_counterbalanced(self, db):
        n = len(sf.all_variants())
        users = [_signup(db, f"u{i}") for i in range(n)]

        positions = {}
        for u in users:
            for pos, variant in enumerate(u["variant_sequence"]):
                positions.setdefault(variant, []).append(pos)
        for seen in positions.values():
            assert sorted(seen) == list(range(n))

    def test_assigned_var_is_the_first_variant(self, db):
        user = _signup(db, "u1")
        assert user["assigned_var"] == user["variant_sequence"][0]

    def test_counter_advances_once_per_signup(self, db):
        for i in range(3):
            _signup(db, f"u{i}")
        counter = db["counters"].find_one({"_id": sf.ROUND_ROBIN_COUNTER_ID})
        assert counter["seq"] == 3

    def test_override_pins_the_first_variant(self, db):
        flow = sf.assign_flow(db, forced_first="links")
        assert flow["variant_sequence"][0] == "links"
        assert flow["assigned_var"] == "links"
        assert flow["assignment_source"] == "override"
        assert sorted(flow["variant_sequence"]) == sorted(sf.all_variants())

    def test_override_does_not_advance_the_rotation_counter(self, db):
        sf.assign_flow(db, forced_first="links")
        assert db["counters"].find_one({"_id": sf.ROUND_ROBIN_COUNTER_ID}) is None

    def test_unknown_override_falls_back_to_rotation(self, db):
        flow = sf.assign_flow(db, forced_first="not_a_variant")
        assert flow["assignment_source"] == "rotation"

    def test_single_variant_mode_reproduces_the_original_flow(self, db):
        sf.save_study_config(db, mode=sf.MODE_SINGLE_VARIANT)
        flow = sf.assign_flow(db)
        assert len(flow["variant_sequence"]) == 1
        assert len(flow["step_order"]) == 5

    def test_no_variants_configured_still_yields_a_base_flow(self, db, monkeypatch):
        monkeypatch.setattr(sf, "all_variants", lambda: [])
        flow = sf.assign_flow(db)
        assert flow["variant_sequence"] == []
        assert flow["assigned_var"] == AssignedVar.followup.value


# ── Progress ─────────────────────────────────────────────────────────────────

class TestProgress:
    def test_walks_every_step_in_order(self, db, config):
        order = sf.build_step_order(sf.variant_sequence_for_seq(1, config))
        doc = {"step_order": order, "completed_steps": []}

        seen = []
        while (step_id := sf.next_step_id(doc)) is not None:
            seen.append(step_id)
            # Only the current step is ever unlocked.
            for other in order:
                assert sf.is_step_unlocked(doc, other) == (other == step_id)
            doc["completed_steps"] = doc["completed_steps"] + [step_id]

        assert seen == order
        assert sf.next_step(doc) is None

    def test_next_step_returns_the_registry_entry(self, config):
        order = sf.build_step_order(sf.variant_sequence_for_seq(1, config))
        assert sf.next_step({"step_order": order, "completed_steps": []}).id == order[0]

    def test_empty_flow_has_no_next_step(self):
        assert sf.next_step_id({}) is None
        assert sf.next_step_id_from(None, None) is None

    def test_is_step_unlocked_for_matches_the_doc_form(self, config):
        order = sf.build_step_order(sf.variant_sequence_for_seq(1, config))
        assert sf.is_step_unlocked_for(order, [], order[0]) is True
        assert sf.is_step_unlocked_for(order, [], order[1]) is False


class TestDerivedLegacyFlags:
    def _order(self, config):
        return sf.build_step_order(sf.variant_sequence_for_seq(1, config))

    def test_all_false_at_the_start(self, config):
        flags = sf.derive_legacy_flags({"step_order": self._order(config), "completed_steps": []})
        assert flags["survey_pre_base_completed"] is False
        assert flags["survey_stage"] == SurveyStage.pre_base.value

    def test_all_true_when_finished(self, config):
        order = self._order(config)
        flags = sf.derive_legacy_flags({"step_order": order, "completed_steps": order})
        assert flags["quiz_variant_completed"] is True
        assert flags["survey_post_variant_completed"] is True
        assert flags["survey_stage"] == SurveyStage.complete.value

    def test_variant_flag_requires_every_variant_quiz(self, config):
        order = self._order(config)
        quizzes = [s for s in order if sf.get_step(s).variant and sf.get_step(s).kind == "quiz"]
        partial = {"step_order": order, "completed_steps": quizzes[:-1]}
        assert sf.derive_legacy_flags(partial)["quiz_variant_completed"] is False

    def test_stage_is_post_base_between_base_quiz_and_its_survey(self, config):
        order = self._order(config)
        upto = order.index(sf.survey_step_id(SurveyStage.post_base.value))
        flags = sf.derive_legacy_flags({"step_order": order, "completed_steps": order[:upto]})
        assert flags["survey_stage"] == SurveyStage.post_base.value

    def test_empty_flow_is_treated_as_complete(self):
        assert sf.derive_legacy_flags({})["survey_stage"] == SurveyStage.complete.value


class TestMarkAndUnmarkStep:
    def _user(self, db, completed=None):
        cfg = sf.StudyConfig(variant_order=tuple(sf.all_variants()))
        order = sf.build_step_order(sf.variant_sequence_for_seq(1, cfg))
        oid = ObjectId()
        db["users"].docs.append(
            {"_id": oid, "step_order": order, "completed_steps": list(completed or [])}
        )
        return str(oid), order

    def test_marking_advances_and_refreshes_flags(self, db):
        uid, _ = self._user(db, ["survey:pre_quiz"])
        update = sf.mark_step_completed(db, uid, "quiz:base", datetime.utcnow())
        assert "quiz:base" in update["completed_steps"]
        assert update["quiz_base_completed"] is True

    def test_marking_a_step_outside_the_flow_is_a_no_op(self, db):
        uid, _ = self._user(db)
        assert sf.mark_step_completed(db, uid, "quiz:base2", datetime.utcnow()) == {}

    def test_marking_twice_is_a_no_op(self, db):
        uid, _ = self._user(db, ["survey:pre_quiz"])
        assert sf.mark_step_completed(db, uid, "survey:pre_quiz", datetime.utcnow()) == {}

    def test_unmarking_reopens_the_step(self, db):
        uid, _ = self._user(db, ["survey:pre_quiz", "quiz:base"])
        sf.unmark_step_completed(db, uid, "quiz:base")
        doc = db["users"].find_one({"_id": ObjectId(uid)})
        assert sf.next_step_id(doc) == "quiz:base"

    def test_unmarking_something_not_done_is_a_no_op(self, db):
        uid, _ = self._user(db)
        assert sf.unmark_step_completed(db, uid, "quiz:base") == {}

    def test_missing_user_is_handled(self, db):
        missing = str(ObjectId())
        assert sf.mark_step_completed(db, missing, "quiz:base", datetime.utcnow()) == {}
        assert sf.unmark_step_completed(db, missing, "quiz:base") == {}


# ── Migration of pre-existing accounts ───────────────────────────────────────

class TestEnsureUserFlow:
    def test_mid_study_participant_keeps_their_variant_and_progress(self, db):
        oid = ObjectId()
        db["users"].docs.append({
            "_id": oid,
            "assigned_var": "links",
            "survey_pre_base_completed": True,
            "quiz_base_completed": True,
            "survey_post_base_completed": True,
            "quiz_variant_completed": False,
            "survey_post_variant_completed": False,
        })

        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))

        assert doc["variant_sequence"][0] == "links"
        assert doc["completed_steps"] == [
            "survey:pre_quiz", "quiz:base", "survey:post_base",
        ]
        # Resumes at their own variant rather than restarting.
        assert sf.next_step_id(doc) == "quiz:links"
        # And now owes the other variants too.
        assert len(doc["step_order"]) == 3 + 2 * len(sf.all_variants())

    def test_finished_legacy_participant_is_not_re_asked(self, db):
        oid = ObjectId()
        db["users"].docs.append({
            "_id": oid,
            "assigned_var": "double",
            "survey_pre_base_completed": True,
            "quiz_base_completed": True,
            "survey_post_base_completed": True,
            "quiz_variant_completed": True,
            "survey_post_variant_completed": True,
        })

        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))

        assert "quiz:double" in doc["completed_steps"]
        assert "survey:post_double" in doc["completed_steps"]
        assert sf.next_step_id(doc) is not None  # continues into the remaining variants

    def test_is_idempotent(self, db):
        oid = ObjectId()
        db["users"].docs.append({"_id": oid, "assigned_var": "links"})
        first = dict(sf.ensure_user_flow(db, db["users"].find_one({"_id": oid})))
        second = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))
        assert second["step_order"] == first["step_order"]
        assert second["completed_steps"] == first["completed_steps"]

    def test_backfills_completed_steps_when_only_step_order_exists(self, db):
        oid = ObjectId()
        cfg = sf.StudyConfig(variant_order=tuple(sf.all_variants()))
        order = sf.build_step_order(sf.variant_sequence_for_seq(1, cfg))
        db["users"].docs.append({
            "_id": oid, "assigned_var": "followup",
            "step_order": order, "survey_pre_base_completed": True,
        })

        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))
        assert doc["completed_steps"] == ["survey:pre_quiz"]

    def test_unknown_assigned_var_still_produces_a_flow(self, db):
        oid = ObjectId()
        db["users"].docs.append({"_id": oid, "assigned_var": "retired_variant"})
        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))
        assert doc["step_order"][1] == "quiz:base"
        assert sorted(doc["variant_sequence"]) == sorted(sf.all_variants())

    def test_single_variant_mode_migration_keeps_one_variant(self, db):
        sf.save_study_config(db, mode=sf.MODE_SINGLE_VARIANT)
        oid = ObjectId()
        db["users"].docs.append({"_id": oid, "assigned_var": "links"})
        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))
        assert doc["variant_sequence"] == ["links"]


# ── Admin reorder isolation ──────────────────────────────────────────────────

class TestReorderIsolation:
    def test_reorder_does_not_touch_in_flight_participants(self, db):
        user = _signup(db, "u1")
        before = list(user["step_order"])

        sf.save_study_config(db, variant_order=["links", "double", "followup"],
                             counterbalance=False)

        assert db["users"].find_one({"_id": "u1"})["step_order"] == before

    def test_new_participants_use_the_new_order(self, db):
        sf.save_study_config(db, variant_order=["links", "double", "followup"],
                             counterbalance=False)
        user = _signup(db, "u2")
        assert user["variant_sequence"] == ["links", "double", "followup"]

    def test_flow_version_is_stamped_on_the_participant(self, db):
        cfg = sf.save_study_config(db, counterbalance=False)
        user = _signup(db, "u3")
        assert user["study_flow_version"] == cfg.version
