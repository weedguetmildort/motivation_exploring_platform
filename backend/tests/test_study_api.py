# backend/tests/test_study_api.py
"""FastAPI TestClient integration tests for app/api/study.py.

/study/next is the single authority the frontend uses to decide where a
participant goes, so these cover the whole walk plus the admin config endpoints.
"""
from unittest.mock import MagicMock

from bson import ObjectId

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.study import router as study_router
from app.api.auth import get_current_user
from app.schemas.user import UserPublic
from app.schemas.question import ALL_SET_IDS
from app.services import study_flow as sf
from tests.conftest import participant_at, standard_step_order


# ── local app fixtures ───────────────────────────────────────────────────────

def _app(user, db=None):
    app = FastAPI()
    app.include_router(study_router)
    app.state.db = db if db is not None else MagicMock()
    app.dependency_overrides[get_current_user] = lambda: user
    return app


@pytest.fixture
def order():
    return standard_step_order()


# ── GET /study/next ──────────────────────────────────────────────────────────

class TestGetNextStep:
    def test_first_step_is_the_pre_quiz_survey(self):
        client = TestClient(_app(participant_at()))
        data = client.get("/study/next").json()

        assert data["next_step"]["id"] == "survey:pre_quiz"
        assert data["next_route"] == "/survey?stage=pre_quiz"
        assert data["completed_count"] == 0
        assert data["finished"] is False

    def test_base_quiz_follows_the_pre_quiz_survey(self):
        client = TestClient(_app(participant_at("quiz:base")))
        data = client.get("/study/next").json()

        assert data["next_step"]["id"] == "quiz:base"
        assert data["next_route"] == "/quiz/base"
        assert data["completed_count"] == 1

    def test_walks_the_entire_flow_in_order(self, order):
        for i, step_id in enumerate(order):
            client = TestClient(_app(participant_at(step_id)))
            data = client.get("/study/next").json()
            assert data["next_step"]["id"] == step_id
            assert data["completed_count"] == i
            assert data["total_steps"] == len(order)

    def test_finished_participant_is_sent_to_the_dashboard(self, order):
        user = participant_at()
        user.completed_steps = list(order)
        data = TestClient(_app(user)).get("/study/next").json()

        assert data["next_step"] is None
        assert data["next_route"] == "/dashboard"
        assert data["finished"] is True
        assert data["completed_count"] == len(order)

    def test_participant_with_no_flow_is_finished_not_crashed(self):
        user = UserPublic(id="u1", email="u@test.edu", is_admin=False)
        data = TestClient(_app(user)).get("/study/next").json()

        assert data["finished"] is True
        assert data["total_steps"] == 0

    def test_requires_authentication(self):
        app = FastAPI()
        app.include_router(study_router)
        app.state.db = MagicMock()
        # No dependency override: the real cookie-based dependency runs.
        assert TestClient(app).get("/study/next").status_code == 401


# ── GET /study/flow ──────────────────────────────────────────────────────────

class TestGetFlow:
    def test_returns_every_step_with_completion(self, order):
        client = TestClient(_app(participant_at("quiz:base")))
        data = client.get("/study/flow").json()

        assert [s["id"] for s in data["steps"]] == order
        assert data["steps"][0]["completed"] is True
        assert data["steps"][1]["completed"] is False
        assert data["current_step_id"] == "quiz:base"

    def test_base_quiz_is_always_the_first_quiz(self):
        data = TestClient(_app(participant_at())).get("/study/flow").json()
        quizzes = [s for s in data["steps"] if s["kind"] == "quiz"]
        assert quizzes[0]["id"] == "quiz:base"

    def test_variant_steps_carry_their_variant(self):
        data = TestClient(_app(participant_at())).get("/study/flow").json()
        variant_steps = [s for s in data["steps"] if s["variant"]]
        # One quiz + one survey per variant.
        assert len(variant_steps) == 2 * len(sf.all_variants())

    def test_reports_finished_when_everything_is_done(self, order):
        user = participant_at()
        user.completed_steps = list(order)
        data = TestClient(_app(user)).get("/study/flow").json()

        assert data["finished"] is True
        assert data["current_step_id"] is None
        assert data["completed_count"] == data["total_steps"]

    def test_unknown_step_ids_are_skipped(self, order):
        user = participant_at()
        user.step_order = order + ["quiz:removed_variant"]
        data = TestClient(_app(user)).get("/study/flow").json()

        assert all(s["id"] != "quiz:removed_variant" for s in data["steps"])


# ── /study/config ────────────────────────────────────────────────────────────

def stocked_db(per_set=20):
    """An in-memory bank with enough questions per set for any question settings."""
    from tests.test_study_flow_service import FakeDB
    db = FakeDB()
    for set_id in ALL_SET_IDS:
        for index in range(per_set):
            db["questions"].insert_one({"_id": f"{set_id}{index}", "set": set_id})
    return db

class TestStudyConfigEndpoints:
    @pytest.fixture
    def admin_client(self):
        admin = UserPublic(id="a1", email="admin@test.edu", is_admin=True)
        return TestClient(_app(admin, db=stocked_db()))

    def test_non_admin_is_refused(self):
        client = TestClient(_app(participant_at()))
        assert client.get("/study/config").status_code == 403
        assert client.put("/study/config", json={"counterbalance": False}).status_code == 403

    def test_returns_defaults_and_the_known_variants(self, admin_client):
        data = admin_client.get("/study/config").json()

        assert data["mode"] == "all_variants"
        assert data["counterbalance"] is True
        assert data["known_variants"] == sf.all_variants()
        assert set(data["variant_labels"]) == set(sf.all_variants())

    def test_preview_shows_one_rotation_per_variant(self, admin_client):
        data = admin_client.get("/study/config").json()
        assert len(data["preview"]) == len(sf.all_variants())

    def test_preview_collapses_when_counterbalancing_is_off(self, admin_client):
        data = admin_client.put("/study/config", json={"counterbalance": False}).json()
        assert data["preview"] == [data["variant_order"]]

    def test_single_variant_preview_hands_out_one_each(self, admin_client):
        data = admin_client.put("/study/config", json={"mode": "single_variant"}).json()
        assert all(len(seq) == 1 for seq in data["preview"])

    def test_reordering_is_persisted_and_bumps_the_version(self, admin_client):
        before = admin_client.get("/study/config").json()["version"]
        new_order = list(reversed(sf.all_variants()))

        data = admin_client.put("/study/config", json={"variant_order": new_order}).json()

        assert data["variant_order"] == new_order
        assert data["version"] == before + 1
        assert admin_client.get("/study/config").json()["variant_order"] == new_order

    def test_unknown_variant_is_rejected(self, admin_client):
        resp = admin_client.put("/study/config", json={"variant_order": ["nope"]})
        assert resp.status_code == 400
        assert "nope" in resp.json()["detail"]

    def test_invalid_mode_is_rejected_by_the_schema(self, admin_client):
        assert admin_client.put("/study/config", json={"mode": "sideways"}).status_code == 422

    def test_partial_update_leaves_other_fields_alone(self, admin_client):
        original = admin_client.get("/study/config").json()["variant_order"]
        data = admin_client.put("/study/config", json={"counterbalance": False}).json()
        assert data["variant_order"] == original


# ── /study/config — per-quiz question sets ───────────────────────────────────

class TestQuizSetConfigEndpoints:
    @pytest.fixture
    def admin_client(self):
        admin = UserPublic(id="a1", email="admin@test.edu", is_admin=True)
        return TestClient(_app(admin, db=stocked_db()))

    def test_defaults_to_balanced_random_with_an_empty_map(self, admin_client):
        data = admin_client.get("/study/config").json()

        assert data["quiz_set_mode"] == "balanced_random"
        assert data["quiz_set_map"] == {}

    def test_advertises_the_sets_and_quizzes_the_code_declares(self, admin_client):
        data = admin_client.get("/study/config").json()

        assert data["known_sets"] == list(ALL_SET_IDS)
        # base first, then every variant — the order an admin maps them in.
        assert data["known_quiz_ids"][0] == sf.BASE_QUIZ_ID
        assert set(data["known_quiz_ids"][1:]) == set(sf.all_variants())
        assert set(data["quiz_labels"]) == set(data["known_quiz_ids"])

    def test_saves_a_map_and_bumps_the_version(self, admin_client):
        before = admin_client.get("/study/config").json()["version"]

        data = admin_client.put(
            "/study/config", json={"quiz_set_map": {"base": "a", "followup": "b"}}
        ).json()

        assert data["quiz_set_map"] == {"base": "a", "followup": "b"}
        assert data["version"] == before + 1
        assert admin_client.get("/study/config").json()["quiz_set_map"] == {
            "base": "a", "followup": "b",
        }

    def test_switches_to_random_mode(self, admin_client):
        data = admin_client.put("/study/config", json={"quiz_set_mode": "random"}).json()
        assert data["quiz_set_mode"] == "random"

    def test_switches_to_balanced_random_and_preserves_it(self, admin_client):
        admin_client.put("/study/config", json={"quiz_set_mode": "preset"})
        before = admin_client.get("/study/config").json()["version"]
        response = admin_client.put("/study/config", json={"quiz_set_mode": "balanced_random"})
        assert response.status_code == 200
        assert response.json()["version"] == before + 1
        assert admin_client.get("/study/config").json()["quiz_set_mode"] == "balanced_random"

    def test_rejects_an_unknown_set_letter(self, admin_client):
        resp = admin_client.put("/study/config", json={"quiz_set_map": {"base": "z"}})

        assert resp.status_code == 400
        assert "z" in resp.json()["detail"]

    def test_rejects_an_unknown_quiz_id(self, admin_client):
        resp = admin_client.put(
            "/study/config", json={"quiz_set_map": {"not_a_quiz": "a"}}
        )

        assert resp.status_code == 400
        assert "not_a_quiz" in resp.json()["detail"]

    def test_quizzes_may_share_a_set_when_it_holds_enough_questions(self, admin_client):
        """A participant never sees a question twice, so sharing is safe with 4 × 5 questions."""
        shared = {quiz: "c" for quiz in (sf.BASE_QUIZ_ID, *sf.all_variants())}
        resp = admin_client.put("/study/config", json={"quiz_set_mode": "preset", "quiz_set_map": shared})

        assert resp.status_code == 200
        assert resp.json()["quiz_set_map"] == shared and resp.json()["supply_problems"] == []

    def test_rejects_an_invalid_set_mode_at_the_schema(self, admin_client):
        resp = admin_client.put("/study/config", json={"quiz_set_mode": "sideways"})
        assert resp.status_code == 422

    def test_a_partial_update_leaves_the_map_alone(self, admin_client):
        admin_client.put("/study/config", json={"quiz_set_map": {"base": "a"}})

        data = admin_client.put("/study/config", json={"counterbalance": False}).json()

        assert data["quiz_set_map"] == {"base": "a"}

    def test_clearing_the_map_is_possible(self, admin_client):
        admin_client.put("/study/config", json={"quiz_set_map": {"base": "a"}})

        data = admin_client.put("/study/config", json={"quiz_set_map": {}}).json()

        assert data["quiz_set_map"] == {}

    def test_non_admin_cannot_change_the_map(self):
        client = TestClient(_app(participant_at()))
        resp = client.put("/study/config", json={"quiz_set_map": {"base": "a"}})
        assert resp.status_code == 403


# ── /study/config — question supply and enrolled participants ────────────────

class TestQuestionSupplyEndpoints:
    ADMIN = UserPublic(id="a1", email="admin@test.edu", is_admin=True)
    SHARED_C = {quiz: "c" for quiz in (sf.BASE_QUIZ_ID, *sf.all_variants())}

    def client(self, db):
        return TestClient(_app(self.ADMIN, db=db))

    def test_reports_questions_per_set(self):
        db = stocked_db(per_set=3)
        db["questions"].insert_one({"_id": "loose", "set": None})
        counts = self.client(db).get("/study/config").json()["question_counts"]
        assert counts == {"a": 3, "b": 3, "c": 3, "d": 3, "unassigned": 1, "total": 13}

    def test_refuses_a_shared_set_without_enough_questions(self):
        db = stocked_db(per_set=19)
        resp = self.client(db).put("/study/config", json={"quiz_set_mode": "preset", "quiz_set_map": self.SHARED_C})
        assert resp.status_code == 400
        assert resp.json()["detail"] == (
            "Not enough questions to give every participant different questions in each quiz. "
            "Set C has 19 questions, but 4 quizzes × 5 questions need 20 different ones.")
        assert self.client(db).get("/study/config").json()["quiz_set_map"] == {}

    def test_a_larger_quiz_size_is_checked_too(self):
        db = stocked_db(per_set=20)
        client = self.client(db)
        assert client.put("/study/config", json={"quiz_set_mode": "preset", "quiz_set_map": self.SHARED_C}).status_code == 200
        resp = client.put("/study/config", json={"questions_per_quiz": 6})
        assert resp.status_code == 400 and "4 quizzes × 6 questions need 24" in resp.json()["detail"]

    def test_random_modes_need_a_full_quiz_in_every_set(self):
        db = stocked_db(per_set=5)
        db["questions"].docs = [q for q in db["questions"].docs if not q["_id"].startswith("d")]
        resp = self.client(db).put("/study/config", json={"quiz_set_mode": "random"})
        assert resp.status_code == 400
        assert "Set D has 0 questions; every set needs at least 5" in resp.json()["detail"]

    def test_saved_settings_that_no_longer_fit_are_reported_but_do_not_block_other_edits(self):
        db = stocked_db(per_set=20)
        client = self.client(db)
        client.put("/study/config", json={"quiz_set_mode": "preset", "quiz_set_map": self.SHARED_C})
        db["questions"].docs = [q for q in db["questions"].docs if q["_id"] != "c0"]  # a question was deleted
        data = client.get("/study/config").json()
        assert data["supply_problems"] == ["Set C has 19 questions, but 4 quizzes × 5 questions need 20 different ones."]
        resp = client.put("/study/config", json={"counterbalance": False})
        assert resp.status_code == 200 and resp.json()["supply_problems"]

    def test_announces_this_studys_own_default_mode(self):
        assert self.client(stocked_db()).get("/study/config").json()["default_quiz_set_mode"] is None

    def test_counts_participants_with_quizzes_not_yet_started(self):
        db = stocked_db()
        order = sf.build_step_order(["followup", "double", "links"])
        db["users"].insert_one({"_id": ObjectId(), "step_order": order, "is_admin": False})
        done = ObjectId()
        db["users"].insert_one({"_id": done, "step_order": ["survey:pre_quiz", "quiz:base"], "is_admin": False})
        db["quiz_attempts"].insert_one({"user_id": str(done), "quiz_id": "base"})
        db["users"].insert_one({"_id": ObjectId(), "step_order": order, "is_admin": True})
        assert self.client(db).get("/study/config").json()["enrolled_with_unstarted_quizzes"] == 1

    def test_saving_can_apply_the_sets_to_enrolled_participants(self):
        db = stocked_db()
        uid = ObjectId()
        order = sf.build_step_order(["followup", "double", "links"])
        db["users"].insert_one({"_id": uid, "step_order": order, "is_admin": False,
                                "quiz_set_assignment": {"base": "a", "followup": "b", "double": "c", "links": "d"}})
        db["quiz_attempts"].insert_one({"user_id": str(uid), "quiz_id": "base"})
        client = self.client(db)

        untouched = client.put("/study/config", json={"quiz_set_mode": "preset", "quiz_set_map": self.SHARED_C}).json()
        assert untouched["applied_participants"] is None
        assert db["users"].find_one({"_id": uid})["quiz_set_assignment"]["followup"] == "b"

        applied = client.put("/study/config", json={"apply_to_enrolled": True}).json()
        assert applied["applied_participants"] == 1
        doc = db["users"].find_one({"_id": uid})
        # The started base quiz keeps its set; the rest move to C.
        assert doc["quiz_set_assignment"] == {"base": "a", "followup": "c", "double": "c", "links": "c"}
        assert doc["quiz_set_history"][0]["by"] == "a1" and doc["quiz_set_history"][0]["started"] == ["base"]
