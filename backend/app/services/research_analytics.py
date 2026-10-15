"""Versioned, question-level research dataset. Agreement is descriptive, never causal reliance.

TODO(research-design): Explore collecting an unaided initial answer and confidence
before AI exposure. Decide whether measuring AI-induced answer changes fits the
study goal: forcing an initial decision changes the intervention itself. Until
then do not label answer selections as unaided judgments, or compute harmful /
beneficial switching, appropriate reliance, or confidence calibration.
"""
import re
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median

ANALYSIS_VERSION = "1.0"
REGIONS = ("question", "answers", "submit", "chat", "chat_input", "suggestions", "reference", "agent_A", "agent_B", "other")
INTENTS = {
    "explanation": r"\b(why|how|explain|reasoning|derive|derivation|steps?)\b",
    "double_check": r"\b(double[ -]?check|check again|verify|are you sure|recheck|recalculate|confirm)\b",
    "challenge": r"\b(wrong|incorrect|mistake|error|disagree|doesn.t match|contradict)\b",
    "source_verification": r"\b(source|reference|citation|evidence|link|supporting)\b",
    "alternative": r"\b(alternative|another (way|method|approach)|different (way|method|approach))\b",
    "answer_only": r"\b(just (the )?answer|answer only|which (option|choice|letter))\b",
}


def prompt_intents(text):
    """Exploratory, multilabel keywords; retain original prompts for human validation."""
    return [name for name, pattern in INTENTS.items() if re.search(pattern, text, re.I)] or ["unclassified"]


def iso(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
    return value or ""


def timestamp(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).timestamp()
    return None


def milliseconds(start, end):
    a, b = timestamp(start), timestamp(end)
    return max(0, (b - a) * 1000) if a is not None and b is not None else None


def research_data(db, include_tests=False, include_archived=False):
    users = {str(u["_id"]): u for u in db["users"].find({})}
    attempts = list(db["quiz_attempts"].find({}))
    if include_archived:
        attempts += list(db["quiz_attempt_archive"].find({}))
    attempts = [a for a in attempts if include_tests or not (
        a.get("is_test") or users.get(a["user_id"], {}).get("is_admin") or users.get(a["user_id"], {}).get("is_test"))]
    # One read per collection, then keyed joins; no per-question database queries.
    indexes = {}
    for collection in ("research_events", "messages", "ai_requests", "copy_events", "reports"):
        grouped = defaultdict(list)
        for doc in db[collection].find({}):
            grouped[(doc.get("user_id"), doc.get("conversation_id"), doc.get("question_id"))].append(doc)
        indexes[collection] = grouped
    rows = []
    for attempt in attempts:
        answers = {a["question_id"]: a for a in attempt.get("answers", [])}
        user = users.get(attempt["user_id"], {})
        for position, qid in enumerate(attempt.get("question_order", []), 1):
            key = (attempt["user_id"], attempt.get("conversation_id"), qid)
            answer = answers.get(qid, {})
            snapshot = attempt.get("question_snapshots", {}).get(qid, {})
            submission = answer.get("telemetry_submission") or {}
            cutoff = submission.get("elapsed_ms")
            page = submission.get("page_id")
            events = indexes["research_events"][key]
            # Same-page monotonic time excludes interactions after the submitted
            # decision without depending on the client's wall-clock accuracy.
            before = [e for e in events if e.get("page_id") != page or cutoff is None or e.get("elapsed_ms", 0) <= cutoff]
            by_type = defaultdict(list)
            for event in before:
                by_type[event["event_type"]].append(event)
            answered_at = timestamp(answer.get("answered_at"))
            messages = sorted([m for m in indexes["messages"][key] if m.get("role") == "assistant"
                               and (answered_at is None or (timestamp(m.get("created_at")) or 0) <= answered_at)],
                              key=lambda m: timestamp(m.get("created_at")) or 0)
            requests = sorted([r for r in indexes["ai_requests"][key] if answered_at is None
                               or (timestamp(r.get("started_at")) or 0) <= answered_at],
                              key=lambda r: timestamp(r.get("started_at")) or 0)
            exposed = {(e.get("data", {}).get("request_id"), e.get("data", {}).get("agent", "default"))
                       for e in by_type["ai_message_displayed"]}
            recommendations = []
            for message in messages:
                for agent, choice in (message.get("metadata", {}).get("stated_choice_id") or {}).items():
                    if choice and (message.get("request_id"), agent) in exposed:
                        recommendations.append((message.get("request_id"), agent, choice))
            known_exposures = {(rid, agent) for rid, agent, _ in recommendations}
            unknown_exposures = exposed - known_exposures
            correct_key = snapshot.get("correct_choice_id")
            first_request = messages[0].get("request_id") if messages else None
            first = {agent: choice for rid, agent, choice in recommendations if rid == first_request}
            last = {agent: choice for _, agent, choice in recommendations}
            wrong = {choice for _, _, choice in recommendations if correct_key and choice != correct_key}
            valid_ai = bool(recommendations and correct_key)
            selected = answer.get("choice_id")
            row = {
                "analysis_version": ANALYSIS_VERSION, "participant_id": attempt["user_id"],
                "attempt_id": str(attempt["_id"]), "conversation_id": attempt.get("conversation_id"),
                "study_flow_version": attempt.get("study_flow_version"), "quiz_id": attempt["quiz_id"],
                "variant_position": attempt.get("variant_position"), "question_set": attempt.get("question_set"),
                "question_id": qid, "question_position": position, "question_version": snapshot.get("version"),
                "question_stem": snapshot.get("stem"), "correct_choice_id": correct_key,
                "snapshot_available": bool(snapshot), "attempt_status": attempt.get("status"),
                "archived": bool(attempt.get("archived_at")), "is_test": bool(attempt.get("is_test") or user.get("is_admin") or user.get("is_test")),
                "shown_at": iso(answer.get("shown_at")), "answered_at": iso(answer.get("answered_at")),
                "was_shown": bool(answer.get("shown_at") or by_type["question_visible"]),
                "answered": bool(answer.get("answered_at")), "choice_id": selected,
                "correct": answer.get("marked_correct") if answer.get("answered_at") else None,
                "planned_wrong_ai": qid in attempt.get("incorrect_question_ids", []),
                "server_elapsed_ms": milliseconds(answer.get("shown_at"), answer.get("answered_at")),
                "submission_page_elapsed_ms": cutoff,
                "telemetry_available": bool(events), "telemetry_submission_anchor": bool(page and cutoff is not None),
                "event_count": len(events), "question_page_count": len({e["page_id"] for e in events}),
                "ai_requests": len(requests), "ai_completed_requests": sum(r.get("main_response_completed", False) for r in requests),
                "ai_failed_requests": sum(r.get("status") in ("failed", "interrupted", "started") for r in requests),
                "manual_prompts": sum(r.get("trigger") == "manual" for r in requests),
                "suggested_prompts": sum(r.get("trigger") == "followup_chip" for r in requests),
                "ai_recommendations_exposed": len(recommendations),
                "ai_recommendations_unresolved": len(unknown_exposures),
                "ai_recommendation_detected": bool(recommendations),
                "wrong_ai_exposed": True if wrong else False if valid_ai and not unknown_exposures else None,
                "matched_wrong_ai": selected in wrong if valid_ai and selected and wrong else None,
                "matched_first_ai": selected in first.values() if first and selected else None,
                "matched_latest_ai": selected in last.values() if last and selected else None,
                "first_agents_disagree": first["A"] != first["B"] if "A" in first and "B" in first else None,
                "latest_agents_disagree": last["A"] != last["B"] if "A" in last and "B" in last else None,
                "no_followup_prompts": not any(r.get("trigger") in ("manual", "followup_chip") for r in requests) if requests else None,
                "answer_selection_count": len(by_type["answer_selected"]),
                "submit_clicks": len(by_type["answer_submit_clicked"]),
                "submit_failures": len(by_type["answer_submit_failed"]),
                "chat_clicks": sum(e.get("data", {}).get("region") in ("chat", "chat_input", "agent_A", "agent_B", "suggestions", "reference") for e in by_type["region_click"]),
                "scroll_events": len(by_type["scroll"]),
                "copy_events": len(indexes["copy_events"][key]),
                # Reports currently have no conversation ID; joined below by user + question + quiz.
                "reported_issue": False,
                "model_versions": sorted({m.get("model_version") for m in messages if m.get("model_version")}),
                "prompt_versions": sorted({m.get("prompt_version") for m in messages if m.get("prompt_version")}),
            }
            first_token_waits = [milliseconds(r.get("started_at"), r.get("first_token_at")) for r in requests]
            first_token_waits = [value for value in first_token_waits if value is not None]
            row["median_ai_first_token_wait_ms"] = median(first_token_waits) if first_token_waits else None
            selections = [e.get("data", {}).get("choice_id") for e in sorted(by_type["answer_selected"], key=lambda e: (e["page_id"], e["sequence"]))]
            row["answer_revision_count"] = sum(a != b for a, b in zip(selections, selections[1:]))
            for agent in ("default", "A", "B"):
                row[f"first_ai_choice_{agent}"] = first.get(agent)
                row[f"latest_ai_choice_{agent}"] = last.get(agent)
                row[f"matched_latest_agent_{agent}"] = selected == last[agent] if selected and agent in last else None
            for name in INTENTS:
                row[f"intent_{name}_heuristic"] = sum(name in prompt_intents(r.get("prompt", "")) for r in requests if r.get("trigger") != "auto_question")
            for prefix in ("suggestion", "reference"):
                displayed = {e.get("data", {}).get("item_id") for e in by_type[f"{prefix}_displayed"]} - {None}
                clicked = {e.get("data", {}).get("item_id") for e in by_type[f"{prefix}_clicked"]} - {None}
                row[f"{prefix}s_displayed"] = len(displayed)
                row[f"{prefix}_clicks"] = len(by_type[f"{prefix}_clicked"])
                row[f"{prefix}s_clicked"] = len(displayed & clicked)
                row[f"{prefix}_click_rate"] = len(displayed & clicked) / len(displayed) if displayed else None
                row[f"{prefix}_clicks_without_impression"] = len(clicked - displayed)
            row.update(visible_ms=None, focused_ms=None, active_ms=None, pointer_observed_ms=None)
            for region in REGIONS:
                row[f"pointer_{region}_ms"] = None
            intervals = [e for e in events if e["event_type"] == "activity_interval"]
            if intervals:
                row.update(visible_ms=0.0, focused_ms=0.0, active_ms=0.0, pointer_observed_ms=0.0)
                for region in REGIONS:
                    row[f"pointer_{region}_ms"] = 0.0
                for event in intervals:
                    data = event.get("data", {})
                    duration = data.get("duration_ms", 0)
                    end = event.get("elapsed_ms", 0)
                    allowed = max(0, min(duration, cutoff - (end - duration))) if event.get("page_id") == page and cutoff is not None else duration
                    scale = allowed / duration if duration else 0
                    for metric in ("visible_ms", "focused_ms", "active_ms"):
                        row[metric] += min(duration, data.get(metric, 0)) * scale
                    pointer = min(duration, data.get("pointer_ms", 0)) * scale
                    row["pointer_observed_ms"] += pointer
                    row[f"pointer_{data.get('region', 'other')}_ms"] += pointer
            # Latency uses the submission page's monotonic timeline, not server/client clock subtraction.
            completions = [e for e in by_type["ai_response_completed"] if e.get("page_id") == page]
            row["last_ai_to_submit_ms"] = cutoff - max(e["elapsed_ms"] for e in completions) if completions and cutoff is not None else None
            gaps = 0
            pages = defaultdict(set)
            for event in events:
                pages[event["page_id"]].add(event["sequence"])
            for seq in pages.values():
                gaps += max(seq) + 1 - len(seq)
            row["event_sequence_gaps"] = gaps
            row["quality_flags"] = [name for name, missing in (
                ("missing_snapshot", not snapshot), ("missing_telemetry", not events),
                ("missing_submission_anchor", bool(answer.get("answered_at")) and not row["telemetry_submission_anchor"]),
                ("event_sequence_gaps", bool(gaps)), ("unresolved_ai_request", bool(row["ai_failed_requests"])),
                ("unresolved_exposed_recommendation", bool(unknown_exposures)),
                ("message_persistence_failure", any(r.get("assistant_message_persisted") is False or r.get("user_message_persisted") is False for r in requests)),
                ("multiple_pages", row["question_page_count"] > 1),
                ("unknown_ai_recommendation", bool(messages) and not recommendations)) if missing]
            rows.append(row)
    reports = list(db["reports"].find({}))
    for row in rows:
        row["reported_issue"] = any(r.get("user_id") == row["participant_id"] and r.get("quiz_id") == row["quiz_id"]
                                    and r.get("question_id") == row["question_id"] for r in reports)
    return rows


def variant_summaries(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["participant_id"], row["attempt_id"])].append(row)
    summaries = []
    for group in groups.values():
        first = group[0]
        answered = [r for r in group if r["answered"]]
        wrong = [r for r in answered if r["wrong_ai_exposed"] is True and r["matched_wrong_ai"] is not None]
        summary = {key: first[key] for key in ("analysis_version", "participant_id", "attempt_id", "quiz_id", "study_flow_version", "variant_position", "question_set", "attempt_status", "archived", "is_test")}
        summary.update(questions_assigned=len(group), questions_shown=sum(r["was_shown"] for r in group),
                       questions_answered=len(answered), correct_answers=sum(r["correct"] is True for r in answered),
                       accuracy=sum(r["correct"] is True for r in answered) / len(answered) if answered else None,
                       wrong_ai_exposure_questions=len(wrong), wrong_ai_matching_answers=sum(r["matched_wrong_ai"] is True for r in wrong),
                       wrong_ai_agreement_rate=sum(r["matched_wrong_ai"] is True for r in wrong) / len(wrong) if wrong else None,
                       telemetry_questions=sum(r["telemetry_available"] for r in group),
                       questions_with_quality_flags=sum(bool(r["quality_flags"]) for r in group))
        for metric in ("active_ms", "visible_ms", "pointer_observed_ms", "last_ai_to_submit_ms", *[f"pointer_{region}_ms" for region in REGIONS]):
            values = [r[metric] for r in group if r[metric] is not None]
            summary[f"median_{metric}"] = median(values) if values else None
        for prefix in ("suggestion", "reference"):
            displayed = sum(r[f"{prefix}s_displayed"] for r in group)
            clicked = sum(r[f"{prefix}s_clicked"] for r in group)
            summary[f"{prefix}s_displayed"] = displayed
            summary[f"{prefix}s_clicked"] = clicked
            summary[f"{prefix}_click_rate"] = clicked / displayed if displayed else None
        for metric in ("manual_prompts", "suggested_prompts", "ai_failed_requests", "chat_clicks", "copy_events", "answer_revision_count", "ai_recommendations_unresolved", *[f"intent_{name}_heuristic" for name in INTENTS]):
            summary[metric] = sum(r[metric] for r in group)
        summaries.append(summary)
    return summaries
