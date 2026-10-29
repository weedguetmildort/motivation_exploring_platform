# backend/tests/test_study_flow_service.py
"""Unit tests for app/services/study_flow.py — the participant flow engine.

Uses a tiny in-memory Mongo double rather than MagicMock for the stateful paths
(assignment, progress, migration), because those read back what they just wrote.
"""
from datetime import datetime
import types

from bson import ObjectId
import pytest

from app.schemas.question import ALL_SET_IDS
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
            d.update(update.get("$setOnInsert", {}))
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

    def test_legacy_post_variant_stage_stays_readable(self):
        assert sf.is_known_survey_stage(SurveyStage.post_variant.value)

    def test_quiz2_ids_are_not_part_of_the_main_flow(self):
        """Phase 13 follow-up study is a separate, admin-granted track."""
        for quiz_id in ("base2", "followup2", "links2", "double2"):
            assert not sf.is_known_quiz_id(quiz_id)

    def test_unknown_ids_are_rejected(self):
        assert sf.get_step("quiz:nope") is None
        assert not sf.is_known_survey_stage("nope")

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
            {
                "_id": oid, "step_order": order,
                "completed_steps": list(completed or []), "quiz_set_assignment": {},
            }
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

    @staticmethod
    def _race(db, uid, concurrent):
        """Let ``concurrent`` write between this request's read and its write."""
        users = db["users"]
        write = users.update_one
        raced = []

        def update_one(q, update, upsert=False):
            if "completed_steps" in q and not raced:
                raced.append(True)
                concurrent(users.find_one({"_id": ObjectId(uid)}))
            return write(q, update, upsert=upsert)

        users.update_one = update_one

    def test_a_step_completed_concurrently_is_not_lost(self, db):
        uid, _ = self._user(db, ["survey:pre_quiz"])
        # e.g. a second tab finishing another step at the same moment.
        self._race(db, uid, lambda doc: doc.update(completed_steps=["survey:pre_quiz", "survey:post_base"]))
        update = sf.mark_step_completed(db, uid, "quiz:base", datetime.utcnow())
        stored = db["users"].find_one({"_id": ObjectId(uid)})
        assert stored["completed_steps"] == ["survey:pre_quiz", "survey:post_base", "quiz:base"]
        assert update["completed_steps"] == stored["completed_steps"]
        assert stored["quiz_base_completed"] is True and stored["survey_post_base_completed"] is True

    def test_an_admin_reset_racing_a_completion_keeps_the_completion(self, db):
        uid, _ = self._user(db, ["survey:pre_quiz", "quiz:base"])
        self._race(db, uid, lambda doc: doc.update(completed_steps=["survey:pre_quiz", "quiz:base", "survey:post_base"]))
        sf.unmark_step_completed(db, uid, "quiz:base")
        stored = db["users"].find_one({"_id": ObjectId(uid)})
        assert stored["completed_steps"] == ["survey:pre_quiz", "survey:post_base"]
        assert stored["quiz_base_completed"] is False

    def test_the_same_step_completed_twice_concurrently_is_recorded_once(self, db):
        uid, _ = self._user(db, ["survey:pre_quiz"])
        self._race(db, uid, lambda doc: doc.update(completed_steps=["survey:pre_quiz", "quiz:base"]))
        assert sf.mark_step_completed(db, uid, "quiz:base", datetime.utcnow()) == {}
        assert db["users"].find_one({"_id": ObjectId(uid)})["completed_steps"] == ["survey:pre_quiz", "quiz:base"]

    def test_a_user_deleted_mid_write_is_handled(self, db):
        uid, _ = self._user(db, ["survey:pre_quiz"])
        self._race(db, uid, lambda doc: db["users"].docs.remove(doc))
        assert sf.mark_step_completed(db, uid, "quiz:base", datetime.utcnow()) == {}

    def test_writes_that_never_land_raise_instead_of_dropping_progress(self, db):
        uid, _ = self._user(db, ["survey:pre_quiz"])
        db["users"].update_one = lambda *a, **k: types.SimpleNamespace(matched_count=0)
        with pytest.raises(RuntimeError):
            sf.mark_step_completed(db, uid, "quiz:base", datetime.utcnow())

    def test_the_write_is_conditional_on_the_list_it_read(self, db):
        uid, _ = self._user(db, ["survey:pre_quiz"])
        calls = []
        write = db["users"].update_one
        db["users"].update_one = lambda q, update, upsert=False: calls.append(q) or write(q, update, upsert=upsert)
        sf.mark_step_completed(db, uid, "quiz:base", datetime.utcnow())
        assert calls[-1] == {"_id": ObjectId(uid), "completed_steps": ["survey:pre_quiz"]}


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

    def test_user_without_a_protocol_gets_the_studys_final_survey(self, db):
        # Study 1 asks one final survey; a rebuild must not invent per-variant ones.
        sf.save_study_config(db, mode=sf.MODE_SINGLE_VARIANT, variant_survey_mode="end_only")
        oid = ObjectId()
        db["users"].docs.append({"_id": oid, "assigned_var": "double", "survey_pre_base_completed": True,
                                 "quiz_base_completed": True, "survey_post_base_completed": True,
                                 "quiz_variant_completed": True})
        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))
        assert doc["step_order"] == ["survey:pre_quiz", "quiz:base", "survey:post_base",
                                     "quiz:double", "survey:post_variant"]
        assert sf.next_step_id(doc) == "survey:post_variant"
        assert doc["study_protocol"]["variant_survey_mode"] == "end_only"

    def test_user_without_a_protocol_gets_the_studys_enabled_surveys(self, db):
        sf.save_study_config(db, survey_stages={"post_base": {"name": "Mid", "enabled": False}})
        oid = ObjectId()
        db["users"].docs.append({"_id": oid, "assigned_var": "links"})
        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))
        assert "survey:post_base" not in doc["step_order"]

    def test_a_snapshotted_protocol_still_wins_over_the_current_config(self, db):
        sf.save_study_config(db, variant_survey_mode="end_only")
        oid = ObjectId()
        db["users"].docs.append({"_id": oid, "assigned_var": "links",
                                 "study_protocol": {"variant_survey_mode": "per_variant"}})
        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))
        assert "survey:post_links" in doc["step_order"] and "survey:post_variant" not in doc["step_order"]

    def test_a_protocol_missing_the_survey_mode_falls_back_to_the_config(self, db):
        sf.save_study_config(db, variant_survey_mode="end_only")
        oid = ObjectId()
        db["users"].docs.append({"_id": oid, "assigned_var": "links", "study_protocol": {"questions_per_quiz": 10}})
        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))
        assert doc["step_order"][-1] == "survey:post_variant"


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


# ── Per-quiz question sets ───────────────────────────────────────────────────

def _quiz_ids(config):
    return sf.quiz_ids_in_order(
        sf.build_step_order(sf.variant_sequence_for_seq(1, config))
    )


class TestReconcileQuizSetMap:
    def test_none_yields_empty(self):
        assert sf._reconcile_quiz_set_map(None) == ()

    def test_accepts_a_dict_and_a_pair_iterable(self):
        assert sf._reconcile_quiz_set_map({"base": "a"}) == (("base", "a"),)
        assert sf._reconcile_quiz_set_map([("base", "a")]) == (("base", "a"),)

    def test_drops_unknown_quiz_ids(self):
        """A retired variant leaves a stale entry behind; it must not survive."""
        out = sf._reconcile_quiz_set_map({"base": "a", "retired_variant": "b"})
        assert out == (("base", "a"),)

    def test_drops_unknown_set_letters(self):
        assert sf._reconcile_quiz_set_map({"base": "z"}) == ()

    def test_drops_quiz2_ids(self):
        """The follow-up study is not part of the main flow mapping."""
        assert sf._reconcile_quiz_set_map({"base2": "a"}) == ()

    def test_first_entry_wins_for_a_duplicate_quiz(self):
        out = sf._reconcile_quiz_set_map([("base", "a"), ("base", "b")])
        assert out == (("base", "a"),)

    def test_quiz_set_map_dict_round_trips(self):
        cfg = sf.StudyConfig(quiz_set_map=(("base", "a"),))
        assert sf.quiz_set_map_dict(cfg) == {"base": "a"}


class TestQuizIdsInOrder:
    def test_returns_quiz_keys_in_flow_order(self, config):
        order = sf.build_step_order(sf.variant_sequence_for_seq(1, config))
        ids = sf.quiz_ids_in_order(order)
        assert ids[0] == sf.BASE_QUIZ_ID
        assert len(ids) == 1 + len(config.variant_order)

    def test_ignores_surveys_and_unknown_steps(self, config):
        order = sf.build_step_order(sf.variant_sequence_for_seq(1, config))
        assert sf.quiz_ids_in_order(order + ["quiz:gone"]) == sf.quiz_ids_in_order(order)


class TestResolveQuizSetAssignment:
    def test_preset_uses_the_configured_map(self, config):
        cfg = sf.StudyConfig(
            variant_order=config.variant_order,
            quiz_set_mode=sf.QUIZ_SET_MODE_PRESET,
            quiz_set_map=(("base", "a"), ("followup", "b")),
        )
        assert sf.resolve_quiz_set_assignment(cfg, _quiz_ids(cfg)) == {
            "base": "a", "followup": "b",
        }

    def test_preset_leaves_unmapped_quizzes_out(self, config):
        """An unmapped quiz draws from the whole pool, so it must be absent."""
        cfg = sf.StudyConfig(
            variant_order=config.variant_order, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET,
            quiz_set_map=(("base", "a"),)
        )
        assignment = sf.resolve_quiz_set_assignment(cfg, _quiz_ids(cfg))
        assert set(assignment) == {"base"}

    def test_preset_ignores_a_quiz_this_participant_does_not_take(self, config):
        cfg = sf.StudyConfig(
            variant_order=config.variant_order,
            quiz_set_mode=sf.QUIZ_SET_MODE_PRESET,
            quiz_set_map=(("base", "a"), ("links", "c")),
        )
        assert sf.resolve_quiz_set_assignment(cfg, ["base"]) == {"base": "a"}

    def test_random_gives_every_quiz_a_distinct_set(self, config):
        cfg = sf.StudyConfig(
            variant_order=config.variant_order,
            quiz_set_mode=sf.QUIZ_SET_MODE_RANDOM,
        )
        quiz_ids = _quiz_ids(cfg)
        assignment = sf.resolve_quiz_set_assignment(cfg, quiz_ids)

        assert set(assignment) == set(quiz_ids)
        # Distinct sets is the whole point - a shared set would allow repeats.
        assert len(set(assignment.values())) == len(assignment)
        assert set(assignment.values()) <= set(ALL_SET_IDS)

    def test_random_varies_across_participants(self, config):
        cfg = sf.StudyConfig(
            variant_order=config.variant_order,
            quiz_set_mode=sf.QUIZ_SET_MODE_RANDOM,
        )
        quiz_ids = _quiz_ids(cfg)
        seen = {
            tuple(sorted(sf.resolve_quiz_set_assignment(cfg, quiz_ids).items()))
            for _ in range(40)
        }
        assert len(seen) > 1

    def test_random_ignores_the_preset_map(self, config):
        cfg = sf.StudyConfig(
            variant_order=config.variant_order,
            quiz_set_mode=sf.QUIZ_SET_MODE_RANDOM,
            quiz_set_map=(("base", "a"),),
        )
        assignment = sf.resolve_quiz_set_assignment(cfg, _quiz_ids(cfg))
        assert len(assignment) == len(_quiz_ids(cfg))

    def test_random_with_more_quizzes_than_sets_leaves_the_rest_unmapped(self):
        cfg = sf.StudyConfig(quiz_set_mode=sf.QUIZ_SET_MODE_RANDOM)
        quiz_ids = ["q%d" % i for i in range(len(ALL_SET_IDS) + 2)]
        assignment = sf.resolve_quiz_set_assignment(cfg, quiz_ids)
        assert len(assignment) == len(ALL_SET_IDS)


class TestQuizSetConfigPersistence:
    def test_defaults_to_balanced_random_with_no_map(self, db):
        cfg = sf.load_study_config(db)
        assert cfg.quiz_set_mode == sf.QUIZ_SET_MODE_BALANCED_RANDOM
        assert cfg.quiz_set_map == ()

    def test_saves_and_reloads_the_map(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "a", "followup": "b"})
        assert sf.quiz_set_map_dict(sf.load_study_config(db)) == {
            "base": "a", "followup": "b",
        }

    def test_changing_the_map_bumps_the_version(self, db):
        before = sf.load_study_config(db).version
        after = sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "a"})
        assert after.version == before + 1

    def test_changing_the_set_mode_bumps_the_version(self, db):
        before = sf.load_study_config(db).version
        after = sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_RANDOM)
        assert after.version == before + 1

    def test_saving_the_same_map_does_not_bump(self, db):
        first = sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "a"})
        second = sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "a"})
        assert second.version == first.version

    def test_invalid_set_mode_falls_back(self, db):
        sf.save_study_config(db, quiz_set_mode="sideways")
        assert sf.load_study_config(db).quiz_set_mode == sf.QUIZ_SET_MODE_BALANCED_RANDOM

    def test_stored_bad_set_mode_is_normalised_on_read(self, db):
        db["study_config"].docs.append(
            {"_id": sf.STUDY_CONFIG_ID, "quiz_set_mode": "bogus"}
        )
        assert sf.load_study_config(db).quiz_set_mode == sf.QUIZ_SET_MODE_BALANCED_RANDOM

    def test_stale_map_entries_are_dropped_on_read(self, db):
        db["study_config"].docs.append(
            {"_id": sf.STUDY_CONFIG_ID, "quiz_set_map": {"base": "a", "gone": "b"}}
        )
        assert sf.quiz_set_map_dict(sf.load_study_config(db)) == {"base": "a"}

    def test_other_fields_are_untouched_by_a_set_only_save(self, db):
        sf.save_study_config(db, counterbalance=False)
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "a"})
        assert sf.load_study_config(db).counterbalance is False

    def test_as_dict_includes_the_set_fields(self):
        cfg = sf.StudyConfig(quiz_set_map=(("base", "a"),))
        assert cfg.as_dict()["quiz_set_map"] == {"base": "a"}
        assert cfg.as_dict()["quiz_set_mode"] == sf.QUIZ_SET_MODE_BALANCED_RANDOM


class TestBalancedRandomAssignment:
    @pytest.mark.parametrize("counterbalance", [True, False])
    @pytest.mark.parametrize("mode", [sf.MODE_ALL_VARIANTS, sf.MODE_SINGLE_VARIANT])
    def test_sets_are_balanced_within_each_order_across_multiple_blocks(
        self, db, counterbalance, mode
    ):
        from collections import Counter, defaultdict

        sf.save_study_config(db, mode=mode, counterbalance=counterbalance)
        grouped = defaultdict(list)
        # Two complete blocks per order; fixed order needs only eight users.
        orders = len(sf.all_variants()) if counterbalance else 1
        for _ in range(orders * len(ALL_SET_IDS) * 2):
            flow = sf.assign_flow(db)
            ids = sf.quiz_ids_in_order(flow["step_order"])
            mapping = flow["quiz_set_assignment"]
            assert set(mapping) == set(ids)
            assert len(set(mapping.values())) == len(mapping)
            grouped[tuple(ids)].append(mapping)

        assert len(grouped) == orders
        for ids, mappings in grouped.items():
            for start in (0, len(ALL_SET_IDS)):
                for quiz_id in ids:
                    assert Counter(m[quiz_id] for m in mappings[start:start + len(ALL_SET_IDS)]) == Counter(ALL_SET_IDS)

    def test_seed_and_block_schedule_survive_a_worker_restart(self, db):
        from copy import deepcopy

        cfg = sf.load_study_config(db)
        ids = _quiz_ids(cfg)
        sf.resolve_quiz_set_assignment(cfg, ids, db=db)
        other_worker = FakeDB()
        other_worker.cols = deepcopy(db.cols)
        expected = [sf.resolve_quiz_set_assignment(cfg, ids, db=db) for _ in range(7)]
        actual = [sf.resolve_quiz_set_assignment(cfg, ids, db=other_worker) for _ in range(7)]
        assert actual == expected

    def test_slot_claim_is_atomic_and_seed_is_initialized_only_once(self, db, mocker):
        cfg = sf.load_study_config(db)
        ids = _quiz_ids(cfg)
        counter = db["counters"]
        spy = mocker.spy(counter, "find_one_and_update")
        sf.resolve_quiz_set_assignment(cfg, ids, db=db)
        first_seed = counter.docs[0]["seed"]
        sf.resolve_quiz_set_assignment(cfg, ids, db=db)
        assert counter.docs[0]["seed"] == first_seed
        assert counter.docs[0]["seq"] == 2
        assert spy.call_args.kwargs == {"upsert": True, "return_document": sf.ReturnDocument.AFTER}
        assert spy.call_args.args[1]["$inc"] == {"seq": 1}
        assert "seed" in spy.call_args.args[1]["$setOnInsert"]

    def test_blocks_are_randomized_not_the_same_fixed_rotation(self, db):
        cfg = sf.load_study_config(db)
        ids = _quiz_ids(cfg)
        # Pin the seed to make this a deterministic regression check.
        sf.resolve_quiz_set_assignment(cfg, ids, db=db)
        db["counters"].docs[0].update(seed="test-seed", seq=0)
        schedules = []
        for _ in range(3):
            schedules.append([
                tuple(sf.resolve_quiz_set_assignment(cfg, ids, db=db).values())
                for _ in ALL_SET_IDS
            ])
        assert schedules[0] != schedules[1]
        assert schedules[1] != schedules[2]

    def test_overrides_do_not_advance_the_quiz_order_counter(self, db):
        flows = [sf.assign_flow(db, forced_first="links") for _ in ALL_SET_IDS]
        assert db["counters"].find_one({"_id": sf.ROUND_ROBIN_COUNTER_ID}) is None
        for quiz_id in flows[0]["quiz_set_assignment"]:
            assert {f["quiz_set_assignment"][quiz_id] for f in flows} == set(ALL_SET_IDS)

    def test_config_version_starts_a_separate_allocation_cohort(self, db):
        sf.assign_flow(db)
        sf.save_study_config(db, counterbalance=False)
        sf.assign_flow(db)
        allocation_counters = [d for d in db["counters"].docs if d["_id"] != sf.ROUND_ROBIN_COUNTER_ID]
        assert len(allocation_counters) == 2
        assert [d["seq"] for d in allocation_counters] == [1, 1]

    def test_reading_or_resetting_does_not_reroll_or_consume_slots(self, db):
        user = _signup(db, ObjectId())
        before = dict(user["quiz_set_assignment"])
        counters = [(d["_id"], d["seq"]) for d in db["counters"].docs]
        sf.ensure_user_flow(db, user)
        sf.repoint_quiz_set(db, str(user["_id"]), "base")
        assert user["quiz_set_assignment"] == before
        assert [(d["_id"], d["seq"]) for d in db["counters"].docs] == counters

    def test_missing_assignment_is_backfilled_once(self, db):
        user = _signup(db, ObjectId())
        del user["quiz_set_assignment"]
        sf.ensure_user_flow(db, user)
        before = dict(user["quiz_set_assignment"])
        sf.ensure_user_flow(db, user)
        assert user["quiz_set_assignment"] == before
        assert len(before) == len(ALL_SET_IDS)

    def test_empty_existing_assignment_is_preserved(self, db):
        user = _signup(db, ObjectId())
        user["quiz_set_assignment"] = {}
        sf.ensure_user_flow(db, user)
        assert user["quiz_set_assignment"] == {}

    def test_explicit_existing_modes_are_preserved(self, db):
        for mode in (sf.QUIZ_SET_MODE_PRESET, sf.QUIZ_SET_MODE_RANDOM):
            sf.save_study_config(db, quiz_set_mode=mode)
            assert sf.load_study_config(db).quiz_set_mode == mode

    def test_unavailable_sets_fail_instead_of_reusing_a_set(self, db):
        with pytest.raises(ValueError, match="at least one question set per quiz"):
            sf.resolve_quiz_set_assignment(sf.load_study_config(db), ["q"] * 5, db=db)

    def test_no_quizzes_uses_no_allocation_slot(self, db):
        assert sf.resolve_quiz_set_assignment(sf.load_study_config(db), [], db=db) == {}
        assert db["counters"].docs == []


class TestQuizSetAssignmentAtSignup:
    def test_preset_map_is_stamped_on_the_participant(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "a", "followup": "b"})
        user = _signup(db, "u1")
        assert user["quiz_set_assignment"]["base"] == "a"
        assert user["quiz_set_assignment"]["followup"] == "b"

    def test_random_mode_gives_each_participant_their_own_mapping(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_RANDOM)
        user = _signup(db, "u1")
        assignment = user["quiz_set_assignment"]
        assert len(assignment) == 1 + len(sf.all_variants())
        assert len(set(assignment.values())) == len(assignment)

    def test_a_later_config_change_does_not_move_an_existing_participant(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "a"})
        before = dict(_signup(db, "u1")["quiz_set_assignment"])

        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "d"})

        assert db["users"].find_one({"_id": "u1"})["quiz_set_assignment"] == before

    def test_assignment_covers_only_the_quizzes_this_participant_takes(self, db):
        full_map = dict(zip([sf.BASE_QUIZ_ID, *sf.all_variants()], ALL_SET_IDS))
        sf.save_study_config(db, mode=sf.MODE_SINGLE_VARIANT, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map=full_map)

        user = _signup(db, "u1")

        # Single-variant flow: base plus one variant only.
        assert set(user["quiz_set_assignment"]) == {
            sf.BASE_QUIZ_ID, user["variant_sequence"][0]
        }


class TestQuizSetAssignmentBackfill:
    @staticmethod
    def _seed_flow_user(db, oid, **extra):
        cfg = sf.load_study_config(db)
        order = sf.build_step_order(sf.variant_sequence_for_seq(1, cfg))
        doc = {"_id": oid, "step_order": order, "completed_steps": []}
        doc.update(extra)
        db["users"].docs.append(doc)
        return order

    def test_backfills_a_participant_assigned_before_sets_existed(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "a"})
        oid = ObjectId()
        self._seed_flow_user(db, oid)

        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))

        assert doc["quiz_set_assignment"] == {"base": "a"}

    def test_backfill_is_idempotent(self, db):
        oid = ObjectId()
        self._seed_flow_user(db, oid)

        first = dict(sf.ensure_user_flow(db, db["users"].find_one({"_id": oid})))
        second = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))

        assert second["quiz_set_assignment"] == first["quiz_set_assignment"]

    def test_an_existing_assignment_is_left_alone(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "d"})
        oid = ObjectId()
        self._seed_flow_user(db, oid, quiz_set_assignment={"base": "a"})

        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))

        assert doc["quiz_set_assignment"] == {"base": "a"}

    def test_legacy_user_without_a_flow_gets_one(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "a"})
        oid = ObjectId()
        db["users"].docs.append({"_id": oid, "assigned_var": "links"})

        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))

        assert doc["quiz_set_assignment"] == {"base": "a"}


class TestEmptyAssignmentIsNotFrozen:
    """An empty assignment means no sets were ever given, so it must stay live.

    Otherwise the map starting empty on deploy would permanently strand every
    existing participant on the whole pool: their next request writes {}, and
    configuring the map afterwards would only ever reach new sign-ups.
    """

    @staticmethod
    def _seed(db, **extra):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET)
        oid = ObjectId()
        cfg = sf.load_study_config(db)
        order = sf.build_step_order(sf.variant_sequence_for_seq(1, cfg))
        doc = {"_id": oid, "step_order": order, "completed_steps": []}
        doc.update(extra)
        db["users"].docs.append(doc)
        return oid

    def test_preset_quiz_set_is_the_draw_time_fallback(self, db):
        """A map configured after the participant was assigned still reaches them.

        ensure_user_flow deliberately does not re-resolve (it runs on every
        request); the draw consults the map instead.
        """
        oid = self._seed(db)
        first = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))
        assert first["quiz_set_assignment"] == {}

        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "a"})

        # The stored snapshot stays empty - no per-request write or config read.
        second = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))
        assert second["quiz_set_assignment"] == {}
        # But the draw picks the map up.
        assert sf.preset_quiz_set(db, "base") == "a"

    def test_preset_fallback_is_none_in_random_mode(self, db):
        """Random mappings live only on the participant, so there is no global
        fallback to reach for."""
        sf.save_study_config(
            db, quiz_set_mode=sf.QUIZ_SET_MODE_RANDOM, quiz_set_map={"base": "a"}
        )
        assert sf.preset_quiz_set(db, "base") is None

    def test_preset_fallback_is_none_for_an_unmapped_quiz(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"followup": "b"})
        assert sf.preset_quiz_set(db, "base") is None

    def test_a_non_empty_assignment_is_never_moved(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "a"})
        oid = self._seed(db, quiz_set_assignment={"base": "b"})

        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))

        assert doc["quiz_set_assignment"] == {"base": "b"}

    def test_stays_empty_while_the_map_is_empty(self, db):
        oid = self._seed(db)
        sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))
        doc = sf.ensure_user_flow(db, db["users"].find_one({"_id": oid}))
        assert doc["quiz_set_assignment"] == {}


class TestRepointQuizSet:
    @staticmethod
    def _seed(db, assignment):
        oid = ObjectId()
        cfg = sf.load_study_config(db)
        order = sf.build_step_order(sf.variant_sequence_for_seq(1, cfg))
        db["users"].docs.append({
            "_id": oid, "step_order": order, "completed_steps": [],
            "quiz_set_assignment": dict(assignment),
        })
        return oid

    def test_picks_up_a_changed_map(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "d"})
        oid = self._seed(db, {"base": "a"})

        assert sf.repoint_quiz_set(db, str(oid), "base") == "d"
        assert db["users"].find_one({"_id": oid})["quiz_set_assignment"]["base"] == "d"

    def test_leaves_other_quizzes_alone(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "d", "followup": "b"})
        oid = self._seed(db, {"base": "a", "followup": "b"})

        sf.repoint_quiz_set(db, str(oid), "base")

        assert db["users"].find_one({"_id": oid})["quiz_set_assignment"] == {
            "base": "d", "followup": "b",
        }

    def test_unmapping_a_quiz_drops_it(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"followup": "b"})
        oid = self._seed(db, {"base": "a", "followup": "b"})

        assert sf.repoint_quiz_set(db, str(oid), "base") is None
        assert "base" not in db["users"].find_one({"_id": oid})["quiz_set_assignment"]

    def test_random_mode_keeps_the_participants_shuffle(self, db):
        """Re-rolling one quiz could collide with another quiz's set."""
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_RANDOM)
        oid = self._seed(db, {"base": "a", "followup": "b"})

        assert sf.repoint_quiz_set(db, str(oid), "base") == "a"
        assert db["users"].find_one({"_id": oid})["quiz_set_assignment"]["base"] == "a"

    def test_missing_user_is_handled(self, db):
        sf.save_study_config(db, quiz_set_mode=sf.QUIZ_SET_MODE_PRESET, quiz_set_map={"base": "a"})
        assert sf.repoint_quiz_set(db, str(ObjectId()), "base") is None
