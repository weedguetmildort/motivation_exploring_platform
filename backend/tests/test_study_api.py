# backend/tests/test_study_api.py
"""FastAPI TestClient integration tests for app/api/study.py.

/study/next is the single authority the frontend uses to decide where a
participant goes, so these cover the whole walk plus the admin config endpoints.
"""
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.study import router as study_router
from app.api.auth import get_current_user
from app.schemas.user import UserPublic
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

class TestStudyConfigEndpoints:
    @pytest.fixture
    def admin_client(self):
        from tests.test_study_flow_service import FakeDB

        admin = UserPublic(id="a1", email="admin@test.edu", is_admin=True)
        return TestClient(_app(admin, db=FakeDB()))

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
