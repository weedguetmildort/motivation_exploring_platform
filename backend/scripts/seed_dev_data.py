"""Seed (or purge) dev dummy data for testing the admin panels, analytics, and
exports. DEV ONLY — refuses to run unless the target DB name ends in "dev".

Usage (from the backend/ directory, with the repo venv):
    python -m scripts.seed_dev_data                  # create 36 dummy participants
    python -m scripts.seed_dev_data --count 10       # create 10
    python -m scripts.seed_dev_data --seed 1         # reproducible fabrication
    python -m scripts.seed_dev_data --purge          # remove all dummy data

Dummies are created through the real ``create_user`` service — intentionally, so
seeding consumes the real ``user_signup_round_robin`` counter (and any pending
next-assignment override), letting us observe assignment behavior under load.

All dummy accounts use emails of the form ``dummy+<n>@example.com`` so the purge
can target them precisely without touching real participants. Related docs
(survey_responses, quiz_attempts, messages, copy_events, link_clicks, reports)
are keyed by the dummy users' id/email so they are cleaned up together. All
dummies share the password ``dummydummy`` (recorded in credentials.md, since
argon2 hashes are not recoverable).
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
# .test / .invalid etc. are rejected by email-validator (reserved TLDs) inside
# create_user's UserPublic(email=...); example.com validates. The "dummy+" local
# part keeps them distinct from the dev.* accounts and precisely purge-able.
DUMMY_EMAIL_DOMAIN = "@example.com"
DUMMY_PASSWORD = "dummydummy"
ADMIN_COMMENT_EMAIL = "dev.admin@example.com"
TRIGGERS = ["ask", "hint", "explain", "followup"]
# Mix of restrictions so the Phase-11 set feature has coverage; None = no restriction.
QUIZ_SET_OPTIONS = [None, ["a"], ["b"], ["c"], ["d"], ["a", "b"], ["a", "b", "c"]]

REPORT_CATEGORIES = ["bug", "unclear_question", "wrong_answer", "technical", "other"]
REPORT_STATUSES = ["open", "in_progress", "resolved", "closed"]
REPORT_DESCRIPTIONS = [
    "The submit button didn't respond on my first click.",
    "This question's wording is ambiguous.",
    "I think the marked answer is wrong.",
    "The AI assistant took a long time to respond.",
    "Just leaving general feedback about the flow.",
]

FIRST_NAMES = ["Ada", "Grace", "Alan", "Katherine", "Linus", "Margaret", "Dennis", "Barbara"]
LAST_NAMES = ["Lovelace", "Hopper", "Turing", "Johnson", "Torvalds", "Hamilton", "Ritchie", "Liskov"]


def _now_minus(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


# ── Purge ────────────────────────────────────────────────────────────────────

def purge(db) -> None:
    users = db["users"]
    # Match both the current domain and the earlier @dev.test attempt so any
    # stray partial rows are cleaned up too.
    dummy = list(users.find(
        {"email": {"$regex": r"^dummy\+.*@(example\.com|dev\.test)$"}}, {"_id": 1, "email": 1}
    ))
    ids = [str(u["_id"]) for u in dummy]
    emails = [u["email"] for u in dummy]
    print(f"Purging {len(ids)} dummy participants and their related docs…")

    db["survey_responses"].delete_many({"user_id": {"$in": ids}})
    db["quiz_attempts"].delete_many({"user_id": {"$in": ids}})
    db["reports"].delete_many({"user_id": {"$in": ids}})
    db["messages"].delete_many({"user_email": {"$in": emails}})
    db["copy_events"].delete_many({"user_email": {"$in": emails}})
    db["link_clicks"].delete_many({"user_email": {"$in": emails}})
    users.delete_many({"_id": {"$in": [ObjectId(i) for i in ids]}})
    _forget_credentials()
    print("Purge complete.")


# ── Fabrication helpers ──────────────────────────────────────────────────────

def _fabricate_demographics() -> dict:
    # Matches the real DemographicsPayload shape (api/demographics.py) — note age
    # is stored as a string.
    return {
        "gender": random.choice(["male", "female", "nonbinary", "prefer_not_to_say"]),
        "other_gender": "",
        "race_ethnicity": random.sample(
            ["white", "black", "hispanic", "asian", "native_american", "other"],
            k=random.randint(1, 2)),
        "age": str(random.randint(18, 45)),
        "academic_level": random.choice(["freshman", "sophomore", "junior", "senior", "graduate"]),
        "other_academic_level": "",
        "year": str(random.randint(1, 5)),
        "major": random.choice(["Computer Science", "Mathematics", "Biology", "Psychology", "Engineering"]),
        "other_major": "",
        "class_name": random.choice(["STA2023", "MAC2311", "CGS2531", "PSY2012"]),
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


def _fabricate_quiz_attempt(user_id, email, quiz_id, pool_docs) -> tuple[dict, str, set]:
    """Build a completed attempt drawing only from ``pool_docs`` (already
    filtered to the participant's quiz_sets). Answers use REAL lowercase choice
    ids and ``marked_correct`` is computed against each question's answer key."""
    conv = str(uuid.uuid4())
    now = _now_minus(random.uniform(1, 20))
    chosen = random.sample(pool_docs, min(10, len(pool_docs)))
    order = [str(q["_id"]) for q in chosen]
    # AI-intentional-incorrect designation, matching real _load_or_create_attempt.
    ai_incorrect = set(random.sample(order, min(3, len(order))))

    answers = []
    for q in chosen:
        qid = str(q["_id"])
        correct_id = q.get("correct_choice_id")
        ids = [c["id"] for c in q.get("choices", [])]
        if ids and correct_id in ids and random.random() < 0.7:
            choice = correct_id                      # ~70% answered correctly
        elif ids:
            wrong = [i for i in ids if i != correct_id] or ids
            choice = random.choice(wrong)
        else:
            choice = None
        answers.append({
            "question_id": qid, "shown_at": now, "answered_at": now,
            "choice_id": choice, "marked_correct": choice == correct_id,
        })

    attempt = {
        "user_id": user_id, "user_email": email, "quiz_id": quiz_id,
        "conversation_id": conv, "status": "completed",
        "question_order": order, "incorrect_question_ids": list(ai_incorrect),
        "answers": answers, "created_at": now, "updated_at": now,
    }
    return attempt, conv, ai_incorrect


def _fabricate_message(user_id, email, conv, quiz_id, question, variant, ai_incorrect) -> dict:
    now = _now_minus(random.uniform(1, 20))
    ids = [c["id"] for c in question.get("choices", [])] or ["a", "b", "c", "d"]
    qid = str(question["_id"])
    # Dual-agent variant states a choice per agent (A/B); others a single default.
    if variant == "double":
        stated = {"A": random.choice(ids), "B": random.choice(ids)}
    else:
        stated = {"default": random.choice(ids)}
    return {
        "conversation_id": conv, "user_id": user_id, "user_email": email,
        "role": "assistant", "source": "ai",
        "quiz_id": quiz_id, "question_id": qid,
        "trigger": random.choice(TRIGGERS),
        "content": "Here's how to think about this problem…",
        "metadata": {"stated_choice_id": stated, "answer_incorrectly": qid in ai_incorrect},
        "created_at": now,
    }


def _fabricate_event(user_id, email, conv, quiz_id, question_id, kind) -> dict:
    now = _now_minus(random.uniform(1, 20))
    base = {"user_id": user_id, "user_email": email, "quiz_id": quiz_id,
            "question_id": question_id, "conversation_id": conv}
    if kind == "copy":
        return {**base, "copied_text": "P(A|B) = P(B|A)P(A)/P(B)", "created_at": now}
    return {**base, "url": "https://example.edu/stats/bayes", "clicked_at": now}


def _fabricate_report(user_id, email, quiz_id, question_id) -> dict:
    now = _now_minus(random.uniform(1, 15))
    comments = []
    if random.random() < 0.5:
        comments.append({
            "id": str(uuid.uuid4()), "author_email": ADMIN_COMMENT_EMAIL,
            "is_admin": True, "body": "Thanks for flagging — we're looking into it.",
            "created_at": now,
        })
    return {
        "user_id": user_id, "user_email": email,
        "quiz_id": quiz_id, "question_id": question_id,
        "category": random.choice(REPORT_CATEGORIES),
        "description": random.choice(REPORT_DESCRIPTIONS),
        "status": random.choice(REPORT_STATUSES),
        "comments": comments,
        "created_at": now, "updated_at": now,
    }


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


def _pool_for(questions, quiz_sets):
    """Questions the participant is allowed to draw from (Phase 11 semantics)."""
    if quiz_sets:
        return [q for q in questions if q.get("set") in quiz_sets]
    return questions


def seed(db, count: int) -> int:
    users = db["users"]
    questions = list(db["questions"].find(
        {}, {"_id": 1, "set": 1, "choices": 1, "correct_choice_id": 1}))
    by_id = {str(q["_id"]): q for q in questions}
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

        _, flags, survey_stage = random.choices(_STAGES, weights=[1, 1, 2, 2, 2, 3])[0]
        quiz_sets = random.choice(QUIZ_SET_OPTIONS)
        pool = _pool_for(questions, quiz_sets)

        # Consent state: most agreed; a few abandoned/declined for funnel testing.
        consent_state = random.choices(["agreed", "abandoned", "declined"], weights=[8, 1, 1])[0]
        now = _now_minus(random.uniform(1, 25))
        set_fields = {
            **flags, "survey_stage": survey_stage.value,
            "demographics": _fabricate_demographics(), "quiz_sets": quiz_sets,
            "consent_viewed_at": now,
        }
        set_fields[{"agreed": "consent_agreed_at", "abandoned": "consent_abandoned_at",
                    "declined": "consent_declined_at"}[consent_state]] = now
        users.update_one({"_id": ObjectId(uid)}, {"$set": set_fields})

        # Survey responses for reached stages.
        if flags.get("survey_pre_base_completed") and pre_items:
            db["survey_responses"].insert_one(
                _fabricate_survey_response(uid, email, "pre_quiz", pre_items))
        if flags.get("survey_post_base_completed") and post_items:
            db["survey_responses"].insert_one(
                _fabricate_survey_response(uid, email, "post_base", post_items))

        # Quiz attempts + chat/events for completed quizzes (drawn from the pool).
        if flags.get("quiz_base_completed") and pool:
            attempt, conv, ai_incorrect = _fabricate_quiz_attempt(uid, email, "base", pool)
            db["quiz_attempts"].insert_one(attempt)
            for qid in attempt["question_order"][:3]:
                q = by_id[qid]
                db["messages"].insert_one(
                    _fabricate_message(uid, email, conv, "base", q, variant, ai_incorrect))
                db["copy_events"].insert_one(
                    _fabricate_event(uid, email, conv, "base", qid, "copy"))
                if variant == "links":
                    db["link_clicks"].insert_one(
                        _fabricate_event(uid, email, conv, "base", qid, "link"))
        if flags.get("quiz_variant_completed") and pool:
            attempt, _, _ = _fabricate_quiz_attempt(uid, email, variant, pool)
            db["quiz_attempts"].insert_one(attempt)

        # Reports for ~30% of participants (referencing a real pool question).
        if random.random() < 0.3:
            rq = random.choice(pool) if pool else None
            db["reports"].insert_one(_fabricate_report(
                uid, email, "base" if rq else None, str(rq["_id"]) if rq else None))

        created += 1

    print(f"Seeded {created} dummy participant(s) (of {count} requested).")
    return created


_CRED_MARKER = "## Dummy participants (dev seed)"


def _strip_credentials_block(text: str) -> str:
    """Remove the dummy-credentials section (marker → EOF; it's always appended last)."""
    return text[:text.index(_CRED_MARKER)].rstrip() + "\n" if _CRED_MARKER in text else text


def _record_credentials(count: int) -> None:
    """Write (replacing any prior block) the dummy credentials into credentials.md
    (git-ignored). Idempotent — re-seeding always reflects the current range."""
    path = _REPO_ROOT / "credentials.md"
    text = _strip_credentials_block(path.read_text(encoding="utf-8") if path.exists() else "")
    block = (
        f"\n{_CRED_MARKER}\n\n"
        f"> Generated by `backend/scripts/seed_dev_data.py`. Passwords are argon2-hashed "
        f"at rest and not recoverable, so recorded here. DEV ONLY.\n\n"
        f"- **Emails:** `{DUMMY_EMAIL_PREFIX}0{DUMMY_EMAIL_DOMAIN}` … "
        f"`{DUMMY_EMAIL_PREFIX}{max(count - 1, 0)}{DUMMY_EMAIL_DOMAIN}`\n"
        f"- **Password (all):** `{DUMMY_PASSWORD}`\n"
    )
    path.write_text(text.rstrip() + "\n" + block, encoding="utf-8")
    print(f"Recorded dummy credentials in {path}")


def _forget_credentials() -> None:
    """Drop the dummy-credentials block from credentials.md (used by --purge)."""
    path = _REPO_ROOT / "credentials.md"
    if path.exists():
        path.write_text(_strip_credentials_block(path.read_text(encoding="utf-8")), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed/purge dev dummy data (dev DB only).")
    parser.add_argument("--count", type=int, default=36, help="how many dummy participants to create")
    parser.add_argument("--seed", type=int, default=None, help="seed Python random for reproducible fabrication")
    parser.add_argument("--purge", action="store_true", help="remove all dummy data instead of seeding")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("MONGO_DB", "")
    if not db_name.endswith("dev"):
        raise SystemExit(f"Refusing to run against non-dev DB: {db_name!r}")
    if not mongo_url:
        raise SystemExit("MONGO_URL is not set.")

    if args.seed is not None:
        random.seed(args.seed)

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=15000)
    db = client[db_name]
    print(f"Target DB: {db_name}")

    if args.purge:
        purge(db)
    else:
        created = seed(db, args.count)
        if created:
            _record_credentials(args.count)


if __name__ == "__main__":
    main()
