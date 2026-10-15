"""Admin cohort views. Average participant-level metrics, excluding missing values."""
from collections import defaultdict
from statistics import mean
from math import isfinite

from .research_analytics import REGIONS, INTENTS, research_data, research_attempts, iso

DEMOGRAPHICS = {
    "gender": "Gender", "academic_level": "Academic level", "year": "Year in program",
    "major": "Major / field of study", "class_name": "Class", "race_ethnicity": "Race / ethnicity",
    "other_gender": "Self-described gender", "other_academic_level": "Other academic level",
    "other_major": "Other major",
}
MISSING = "__missing__"


def definition(key, label, group, unit="percent", kind="boolean", field=None, eligibility="answered", numerator=None, denominator=None):
    return dict(key=key, label=label, group=group, unit=unit, kind=kind, field=field or key,
                eligibility=eligibility, numerator=numerator, denominator=denominator)


METRICS = [
    definition("accuracy", "Accuracy", "Performance", field="correct"),
    definition("wrong_ai_agreement", "Agreement with wrong AI", "AI agreement", field="matched_wrong_ai"),
    definition("first_ai_agreement", "Matches first AI answer", "AI agreement", field="matched_first_ai"),
    definition("latest_ai_agreement", "Matches latest AI answer", "AI agreement", field="matched_latest_ai"),
    definition("wrong_ai_exposed", "Questions with observed wrong AI", "AI agreement"),
    definition("planned_wrong_ai", "Questions assigned wrong advice", "AI agreement"),
    definition("no_followup", "No follow-up prompts", "AI agreement", field="no_followup_prompts"),
    definition("first_agents_disagree", "First agents disagree", "AI agreement"),
    definition("latest_agents_disagree", "Latest agents disagree", "AI agreement"),
    definition("matched_latest_agent_A", "Matches latest Agent A", "AI agreement"),
    definition("matched_latest_agent_B", "Matches latest Agent B", "AI agreement"),
]
for field, label in {
    "server_elapsed_ms": "Elapsed time per question", "active_ms": "Active time per question",
    "visible_ms": "Visible page time", "focused_ms": "Focused page time",
    "focused_inactive_ms": "Focused time without recent activity", "last_ai_to_submit_ms": "Last AI completion to submission",
    "median_ai_first_token_wait_ms": "AI first-token wait", "unobserved_timer_ms": "Unobserved suspended-timer time",
}.items():
    METRICS.append(definition(field, label, "Timing", "seconds", "number"))
for field, label in {
    "manual_prompts": "Typed prompts per question", "suggested_prompts": "Suggested prompts per question",
    "ai_requests": "AI requests per question", "ai_failed_requests": "Unresolved AI requests per question",
    "chat_clicks": "Chat clicks per question", "copy_events": "Copies per question",
    "answer_revision_count": "Selection revisions per question", "submit_failures": "Submission failures per question",
    "scroll_events": "Scroll events per question",
}.items():
    METRICS.append(definition(field, label, "Interaction", "count", "number",
                              eligibility="requests" if field in ("manual_prompts", "suggested_prompts", "ai_requests", "ai_failed_requests") else "tracked"))
for name in INTENTS:
    METRICS.append(definition(f"intent_{name}_heuristic", name.replace("_", " ").capitalize() + " prompts", "Verification", "count", "number", eligibility="requests"))
for prefix, label in (("suggestion", "Suggestions used"), ("reference", "References opened")):
    METRICS.append(definition(f"{prefix}_click_rate", label, "Interaction", kind="ratio",
                              numerator=f"{prefix}s_clicked", denominator=f"{prefix}s_displayed"))
for region in REGIONS:
    label = region.replace("_", " ").capitalize()
    METRICS.append(definition(f"pointer_{region}_ms", f"Pointer time: {label}", "Pointer regions", "seconds", "number"))
    METRICS.append(definition(f"pointer_{region}_share", f"Pointer share: {label}", "Pointer regions", kind="ratio",
                              numerator=f"pointer_{region}_ms", denominator="pointer_observed_ms"))
METRICS.extend([
    definition("telemetry_coverage", "Questions with telemetry", "Data quality", field="telemetry_available", eligibility="shown"),
    definition("quality_flag_rate", "Questions with quality flags", "Data quality", field="quality_flags", eligibility="shown"),
    definition("unresolved_recommendations", "Unresolved AI recommendations", "Data quality", "count", "number", field="ai_recommendations_unresolved", eligibility="tracked"),
    definition("reported_issue", "Questions with a reported issue", "Data quality"),
])
for field, label in {
    "student_turns": "Student turns", "student_words": "Student words", "repeated_prompts": "Repeated prompts",
    "reasoning_turns_heuristic": "Reasoning statements (keywords)", "specific_challenges_heuristic": "Specific challenges (keywords)",
    "answer_only_turns_heuristic": "Answer-only requests (keywords)", "mean_ai_response_words": "Saved AI response length",
    "ai_certainty_markers_heuristic": "AI certainty markers (keywords)", "ai_recommendation_changes": "AI answer changes",
    "ai_wrong_to_correct_transitions": "AI wrong-to-correct changes", "ai_correct_to_wrong_transitions": "AI correct-to-wrong changes",
    "verification_suggestions_displayed_heuristic": "Verification suggestions shown (keywords)",
    "verification_suggestions_clicked_heuristic": "Verification suggestions clicked (keywords)",
}.items():
    METRICS.append(definition(field, label, "Conversation", "count", "number"))
for field, label in {
    "challenge_after_wrong_ai_heuristic": "Challenge after wrong AI (keywords)",
    "ai_repair_after_challenge_heuristic": "AI answer corrected after challenge (keywords)",
    "correct_after_ai_repair": "Correct submission after AI repair", "disagreement_followup_heuristic": "Disagreement follow-up (keywords)",
    "agents_converged": "Initially disagreeing agents converged",
}.items():
    METRICS.append(definition(field, label, "Conversation"))


def demographic_values(user, key):
    value = (user.get("demographics") or {}).get(key)
    values = value if isinstance(value, list) else [value]
    return [str(v).strip() for v in values if v is not None and str(v).strip()]


def profile(user):
    return {"participant_id": str(user["_id"]), "email": user.get("email", ""),
            "name": " ".join(str(user.get(k) or "").strip() for k in ("first_name", "last_name")).strip(),
            "demographics": user.get("demographics") or {}, "is_test": bool(user.get("is_admin") or user.get("is_test")),
            "study_flow_version": user.get("study_flow_version"), "completed_steps": user.get("completed_steps", []),
            "step_order": user.get("step_order", []), "created_at": iso(user.get("created_at"))}


def filter_users(users, filters, search="", age_min=None, age_max=None):
    result = []
    query = search.strip().casefold()
    for user in users:
        identity = profile(user)
        if query and query not in " ".join((identity["participant_id"], identity["name"], identity["email"])).casefold():
            continue
        if any(not (not demographic_values(user, key) if selected == MISSING else
                    any(v.casefold() == selected.strip().casefold() for v in demographic_values(user, key)))
               for key, selected in filters.items()):
            continue
        if age_min is not None or age_max is not None:
            try:
                age = float((user.get("demographics") or {}).get("age"))
            except (TypeError, ValueError):
                continue
            if not isfinite(age):
                continue
            if (age_min is not None and age < age_min) or (age_max is not None and age > age_max):
                continue
        result.append(user)
    return result


def filter_rows(rows, quiz_id=None, status="completed", version=None, question_set=None, variant_position=None):
    return [r for r in rows if (not quiz_id or r["quiz_id"] == quiz_id)
            and (status == "all" or r.get("attempt_status", r.get("status")) == status)
            and (version is None or r.get("study_flow_version") == version)
            and (not question_set or r.get("question_set") == question_set)
            and (variant_position is None or r.get("variant_position") == variant_position)]


def aggregate(rows, attempts=None):
    metrics = {}
    for spec in METRICS:
        by_person = defaultdict(list)
        for row in rows:
            eligible = row["was_shown"] if spec["eligibility"] == "shown" else row["answered"]
            if spec["eligibility"] == "tracked":
                eligible = eligible and row["telemetry_available"]
            elif spec["eligibility"] == "requests":
                eligible = eligible and row["ai_requests"] > 0
            if not eligible:
                continue
            if spec["kind"] == "ratio":
                num, den = row.get(spec["numerator"]), row.get(spec["denominator"])
                if num is not None and den is not None and den > 0:
                    by_person[row["participant_id"]].append((num, den))
            else:
                value = row.get(spec["field"])
                if value is not None:
                    by_person[row["participant_id"]].append((float(bool(value)) if spec["kind"] == "boolean" else float(value), 1))
        values = [sum(n for n, _ in observations) / sum(d for _, d in observations) for observations in by_person.values()]
        numerator = sum(n for observations in by_person.values() for n, _ in observations)
        denominator = sum(d for observations in by_person.values() for _, d in observations)
        metrics[spec["key"]] = {
            "value": mean(values) if values else None, "participant_count": len(values),
            "observation_count": sum(map(len, by_person.values())),
            "numerator": numerator if values and spec["kind"] != "number" else None,
            "denominator": denominator if values and spec["kind"] != "number" else None,
            "pooled_value": numerator / denominator if denominator else None,
        }
    by_attempt = defaultdict(list)
    for row in rows:
        if row.get("attempt_id"):
            by_attempt[row["attempt_id"]].append(row)
    selected_attempts = (attempts if attempts is not None else [
        {"_id": aid, "user_id": group[0]["participant_id"], "status": group[0]["attempt_status"]}
        for aid, group in by_attempt.items()
    ])
    answered = sum(r["answered"] for r in rows)
    graded = sum(r["answered"] and isinstance(r.get("correct"), bool) for r in rows)
    return {"participant_count": len({a["user_id"] for a in selected_attempts} | {r["participant_id"] for r in rows}),
            "attempt_count": len(selected_attempts),
            "completed_attempt_count": sum(a.get("status") == "completed" for a in selected_attempts),
            "incomplete_completed_attempt_count": sum(a.get("status") == "completed" and (
                not by_attempt[str(a["_id"])] or any(not r["answered"] for r in by_attempt[str(a["_id"])])
            ) for a in selected_attempts),
            "questions_assigned": len(rows), "questions_shown": sum(r["was_shown"] for r in rows),
            "questions_answered": answered, "questions_graded": graded,
            "answers_missing_grade": answered - graded, "metrics": metrics}


def comparisons(rows, attempts=None):
    variants = sorted({r["quiz_id"] for r in rows} | {a["quiz_id"] for a in (attempts or [])}, key=lambda q: (q != "base", q))
    return [{"quiz_id": variant, **aggregate([r for r in rows if r["quiz_id"] == variant],
             [a for a in attempts if a["quiz_id"] == variant] if attempts is not None else None)} for variant in variants]


def dashboard(db, *, filters, search="", age_min=None, age_max=None, include_tests=False, include_archived=False,
              quiz_id=None, status="completed", version=None, question_set=None, variant_position=None, page=1, page_size=25):
    users = [u for u in db["users"].find({}) if include_tests or not (u.get("is_admin") or u.get("is_test"))]
    facets = []
    for key, label in DEMOGRAPHICS.items():
        counts = defaultdict(int)
        missing = 0
        for user in users:
            values = set(demographic_values(user, key))
            if not values:
                missing += 1
            for value in values:
                counts[value] += 1
        facets.append({"key": key, "label": label, "options": [{"value": v, "count": count} for v, count in sorted(counts.items(), key=lambda item: item[0].casefold())], "missing_count": missing})
    selected = filter_users(users, filters, search, age_min, age_max)
    ids = {str(u["_id"]) for u in selected}
    attempts = filter_rows(research_attempts(db, include_tests, include_archived, participant_ids=ids,
                           users={str(u["_id"]): u for u in selected}), quiz_id, status, version, question_set, variant_position)
    rows = research_data(db, include_tests, include_archived, participant_ids=ids, attempts=attempts)
    by_person = defaultdict(list)
    attempts_by_person = defaultdict(list)
    for attempt in attempts:
        attempts_by_person[attempt["user_id"]].append(attempt)
    for row in rows:
        by_person[row["participant_id"]].append(row)
    # An account with no selected attempts remains searchable and is explicitly
    # distinguished from an account contributing to the cohort averages.
    directory = []
    for user in sorted(selected, key=lambda u: (profile(u)["name"].casefold(), u.get("email", ""), str(u["_id"]))):
        person = profile(user)
        person_rows = by_person[person["participant_id"]]
        score = aggregate(person_rows, attempts_by_person[person["participant_id"]])
        directory.append({**person, "questions_answered": score["questions_answered"],
                          "attempt_count": score["attempt_count"], "questions_graded": score["questions_graded"],
                          "answers_missing_grade": score["answers_missing_grade"],
                          "accuracy": score["metrics"]["accuracy"]["value"],
                          "telemetry_questions": sum(r["telemetry_available"] for r in person_rows)})
    total_pages = (len(directory) + page_size - 1) // page_size
    page = min(page, max(1, total_pages))
    start = (page - 1) * page_size
    choices_query = {"user_id": {"$in": [str(u["_id"]) for u in users]}}
    choices = list(db["quiz_attempts"].find(choices_query, {"quiz_id": 1, "study_flow_version": 1}))
    if include_archived:
        choices += list(db["quiz_attempt_archive"].find(choices_query, {"quiz_id": 1, "study_flow_version": 1}))
    versions = {u.get("study_flow_version") for u in users if isinstance(u.get("study_flow_version"), int)}
    versions.update(a["study_flow_version"] for a in choices if isinstance(a.get("study_flow_version"), int))
    return {"metric_definitions": METRICS, "facets": facets,
            "study_versions": sorted(versions), "quiz_ids": sorted({a["quiz_id"] for a in choices}),
            "matched_accounts": len(selected), "overall": aggregate(rows, attempts), "variants": comparisons(rows, attempts),
            "participants": directory[start:start + page_size], "page": page, "page_size": page_size,
            "total_pages": total_pages,
            "averaging": "Each participant contributes equally. Missing or ineligible measurements are excluded per metric."}
