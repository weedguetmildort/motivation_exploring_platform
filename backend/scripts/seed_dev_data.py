"""Seed (or purge) dev dummy data for testing the admin panels, analytics, and
exports. DEV ONLY — refuses to run unless the target DB name ends in "dev".

Usage (from the backend/ directory, with the repo venv):
    python -m scripts.seed_dev_data --count 30      # create 30 dummy participants
    python -m scripts.seed_dev_data --purge         # remove all dummy data

All dummy accounts use emails of the form ``dummy+<n>@dev.test`` so the purge can
target them precisely without touching real participants. Related docs
(survey_responses, quiz_attempts, messages, copy_events, link_clicks) are keyed
by the dummy users' id/email so they are cleaned up together.

This is a scaffold: it produces realistic-shaped rows across variants, sets,
stages, and consent states. Volume and richness can be tuned via the constants
below or extended as testing needs grow.
"""
from __future__ import annotations

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Load .env so MONGO_URL / MONGO_DB are available when run standalone ──────
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _REPO_ROOT / ".env"
if _ENV_PATH.exists():
    import os
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

import os  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from bson import ObjectId  # noqa: E402

# The service layer creates correctly-shaped, argon2-hashed accounts.
sys.path.insert(0, str(_REPO_ROOT / "backend"))
from app.services.users import create_user  # noqa: E402
from app.schemas.user import SurveyStage  # noqa: E402

DUMMY_EMAIL_PREFIX = "dummy+"
DUMMY_EMAIL_DOMAIN = "@dev.test"
DUMMY_PASSWORD = "dummydummy"
SETS = ["a", "b", "c", "d"]
QUIZ_IDS = ["base", "followup", "links", "double"]
TRIGGERS = ["ask", "hint", "explain", "followup"]

FIRST_NAMES = ["Ada", "Grace", "Alan", "Katherine", "Linus", "Ada", "Margaret", "Dennis"]
LAST_NAMES = ["Lovelace", "Hopper", "Turing", "Johnson", "Torvalds", "Hamilton", "Ritchie"]


def _now_minus(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


# ── Purge ────────────────────────────────────────────────────────────────────

def purge(db) -> None:
    users = db["users"]
    dummy = list(users.find(
        {"email": {"$regex": r"^dummy\+.*@dev\.test$"}}, {"_id": 1, "email": 1}
    ))
    ids = [str(u["_id"]) for u in dummy]
    emails = [u["email"] for u in dummy]
    print(f"Purging {len(ids)} dummy participants and their related docs…")

    db["survey_responses"].delete_many({"user_id": {"$in": ids}})
    db["quiz_attempts"].delete_many({"user_id": {"$in": ids}})
    db["messages"].delete_many({"user_email": {"$in": emails}})
    db["copy_events"].delete_many({"user_email": {"$in": emails}})
    db["link_clicks"].delete_many({"user_email": {"$in": emails}})
    users.delete_many({"_id": {"$in": [ObjectId(i) for i in ids]}})
    print("Purge complete.")


# ── Fabrication helpers ──────────────────────────────────────────────────────

def _fabricate_demographics() -> dict:
    return {
        "age": random.randint(18, 45),
        "gender": random.choice(["male", "female", "nonbinary", "prefer_not"]),
        "academic_level": random.choice(["freshman", "sophomore", "junior", "senior", "grad"]),
        "major": random.choice(["CS", "Math", "Biology", "Psychology", "Engineering"]),
    }


def _fabricate_survey_response(user_id, email, stage, item_ids) -> dict:
    now = _now_minus(random.uniform(1, 20))
    answers = [
        {"item_id": iid, "value": random.randint(1, 5),
         "shown_at": now, "answered_at": now}
        for iid in item_ids
    ]
    return {
        "user_id": user_id, "user_email": email, "stage": stage,
        "status": "completed", "answers": answers,
        "started_at": now, "completed_at": now, "updated_at": now,
    }


def _fabricate_quiz_attempt(user_id, email, quiz_id, question_ids) -> tuple[dict, str]:
    conv = str(uuid.uuid4())
    order = [str(q) for q in random.sample(question_ids, min(10, len(question_ids)))]
    incorrect = random.sample(order, min(3, len(order)))
    now = _now_minus(random.uniform(1, 20))
    answers = []
    for qid in order:
        choice = random.choice(["A", "B", "C", "D"])
        answers.append({
            "question_id": qid, "shown_at": now, "answered_at": now,
            "choice_id": choice, "marked_correct": qid not in incorrect,
        })
    return {
        "user_id": user_id, "user_email": email, "quiz_id": quiz_id,
        "conversation_id": conv, "status": "completed",
        "question_order": order, "incorrect_question_ids": incorrect,
        "answers": answers, "created_at": now, "updated_at": now,
    }, conv


def _fabricate_message(email, conv, quiz_id, question_id) -> dict:
    now = _now_minus(random.uniform(1, 20))
    return {
        "conversation_id": conv, "user_email": email, "role": "assistant",
        "quiz_id": quiz_id, "question_id": question_id,
        "trigger": random.choice(TRIGGERS),
        "content": "Here's how to think about this problem…",
        "metadata": {
            "stated_choice_id": {
                "default": random.choice(["A", "B", "C", "D"]),
                "A": random.choice(["A", "B", "C", "D"]),
                "B": random.choice(["A", "B", "C", "D"]),
            },
            "answer_incorrectly": random.random() < 0.3,
        },
        "created_at": now,
    }


def _fabricate_event(email, quiz_id, question_id, kind) -> dict:
    now = _now_minus(random.uniform(1, 20))
    if kind == "copy":
        return {"user_email": email, "quiz_id": quiz_id, "question_id": question_id,
                "copied_text": "P(A|B) = P(B|A)P(A)/P(B)", "created_at": now}
    return {"user_email": email, "quiz_id": quiz_id, "question_id": question_id,
            "url": "https://example.edu/stats/bayes", "clicked_at": now}


# ── Stage progression: how far through the study each dummy has gotten ────────

_STAGES = [
    # (label, flags to set, survey_stage)
    ("signed_up", {}, SurveyStage.pre_base),
    ("demographics", {"demographics_completed": True}, SurveyStage.pre_base),
    ("pre_survey", {"demographics_completed": True, "survey_pre_base_completed": True}, SurveyStage.pre_base),
    ("quiz_base", {"demographics_completed": True, "survey_pre_base_completed": True,
                   "quiz_base_completed": True}, SurveyStage.post_base),
    ("post_base_survey", {"demographics_completed": True, "survey_pre_base_completed": True,
                          "quiz_base_completed": True, "survey_post_base_completed": True}, SurveyStage.post_base),
    ("complete", {"demographics_completed": True, "survey_pre_base_completed": True,
                  "quiz_base_completed": True, "survey_post_base_completed": True,
                  "quiz_variant_completed": True, "survey_post_variant_completed": True}, SurveyStage.complete),
]


def seed(db, count: int) -> None:
    users = db["users"]
    question_ids = [q["_id"] for q in db["questions"].find({}, {"_id": 1})]
    pre_items = [str(i["_id"]) for i in db["survey_items"].find({"stage": "pre_quiz"}, {"_id": 1})]
    post_items = [str(i["_id"]) for i in db["survey_items"].find({"stage": "post_base"}, {"_id": 1})]

    created = 0
    for n in range(count):
        email = f"{DUMMY_EMAIL_PREFIX}{n}{DUMMY_EMAIL_DOMAIN}"
        if users.find_one({"email": email}):
            continue  # idempotent: skip already-seeded

        pub = create_user(
            users, email=email, password=DUMMY_PASSWORD,
            first_name=random.choice(FIRST_NAMES), last_name=random.choice(LAST_NAMES),
            consent=True,
        )
        uid = pub.id
        variant = pub.assigned_var.value

        stage_label, flags, survey_stage = random.choices(
            _STAGES, weights=[1, 1, 2, 2, 2, 3]
        )[0]

        # Consent state: most agreed; a few abandoned/declined for funnel testing.
        consent_state = random.choices(
            ["agreed", "abandoned", "declined"], weights=[8, 1, 1]
        )[0]
        set_fields = {**flags, "survey_stage": survey_stage.value,
                      "demographics": _fabricate_demographics(),
                      "quiz_sets": random.choice([None, ["a"], ["b"], ["a", "b"]])}
        now = _now_minus(random.uniform(1, 25))
        set_fields["consent_viewed_at"] = now
        if consent_state == "agreed":
            set_fields["consent_agreed_at"] = now
        elif consent_state == "abandoned":
            set_fields["consent_abandoned_at"] = now
        else:
            set_fields["consent_declined_at"] = now
        users.update_one({"_id": ObjectId(uid)}, {"$set": set_fields})

        # Survey responses for reached stages.
        if flags.get("survey_pre_base_completed") and pre_items:
            db["survey_responses"].insert_one(
                _fabricate_survey_response(uid, email, "pre_quiz", pre_items))
        if flags.get("survey_post_base_completed") and post_items:
            db["survey_responses"].insert_one(
                _fabricate_survey_response(uid, email, "post_base", post_items))

        # Quiz attempts + chat/events for completed quizzes.
        if flags.get("quiz_base_completed") and question_ids:
            attempt, conv = _fabricate_quiz_attempt(uid, email, "base", question_ids)
            db["quiz_attempts"].insert_one(attempt)
            for qid in attempt["question_order"][:3]:
                db["messages"].insert_one(_fabricate_message(email, conv, "base", qid))
                db["copy_events"].insert_one(_fabricate_event(email, "base", qid, "copy"))
                if variant == "links":
                    db["link_clicks"].insert_one(_fabricate_event(email, "base", qid, "link"))
        if flags.get("quiz_variant_completed") and question_ids:
            attempt, conv = _fabricate_quiz_attempt(uid, email, variant, question_ids)
            db["quiz_attempts"].insert_one(attempt)

        created += 1

    print(f"Seeded {created} dummy participant(s) (of {count} requested).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed/purge dev dummy data (dev DB only).")
    parser.add_argument("--count", type=int, default=20, help="how many dummy participants to create")
    parser.add_argument("--purge", action="store_true", help="remove all dummy data instead of seeding")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("MONGO_DB", "")
    if not db_name.endswith("dev"):
        raise SystemExit(f"Refusing to run against non-dev DB: {db_name!r}")
    if not mongo_url:
        raise SystemExit("MONGO_URL is not set.")

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=15000)
    db = client[db_name]
    print(f"Target DB: {db_name}")

    if args.purge:
        purge(db)
    else:
        seed(db, args.count)


if __name__ == "__main__":
    main()
