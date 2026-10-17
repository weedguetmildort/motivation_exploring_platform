"""Auditable conversation packets and explicitly exploratory language features."""
import hashlib
import json
import re
from datetime import datetime, timezone
from statistics import mean

PACKET_VERSION = "2"
CHALLENGE = re.compile(r"\b(wrong|incorrect|mistake|error|disagree|doesn.t match|contradict|are you sure|double[ -]?check|recheck)\b", re.I)
SPECIFIC = re.compile(r"\d|\b(denominator|numerator|equation|calculation|subtract|multiply|divide|because|line|step)\b", re.I)
REASONING = re.compile(r"\d\s*[+*/=−-]\s*\d|\b(i calculated|i computed|my calculation|i got|i think.+because|therefore|this means)\b", re.I)
ANSWER_ONLY = re.compile(r"\b(just (the )?answer|answer only|give me (the )?answer|which (option|choice|letter))\b", re.I)
VERIFY = re.compile(r"\b(check|verify|source|evidence|reference|contradict|wrong|error)\b", re.I)
EXPLAIN = re.compile(r"\b(why|how|explain|reason|derive|steps?)\b", re.I)
COMPARE = re.compile(r"\b(disagree|compare|both agents|agent a|agent b|reconcile|different answers)\b", re.I)
CERTAIN = re.compile(r"\b(definitely|certainly|obviously|guaranteed|without (a )?doubt)\b", re.I)


def time_value(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value.replace(tzinfo=value.tzinfo or timezone.utc).timestamp() if isinstance(value, datetime) else None


def stamp(value):
    value = time_value(value)
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value is not None else None


def text_value(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(value for value in content if isinstance(value, str))
    return ""


def build_packet(row, snapshot, messages, requests, events):
    """Only include server-timed turns at/before the submitted answer.

    Persisted assistant replies and viewport-confirmed replies remain distinct.
    Missing timestamps are excluded from sequencing, never guessed to be early.
    Request ledgers recover student prompts whose message persistence failed.
    """
    end = time_value(row.get("answered_at"))
    turns = []
    seen_requests = set()
    exposures = {(e.get("data", {}).get("request_id"), e.get("data", {}).get("agent", "default"))
                 for e in events if e.get("event_type") == "ai_message_displayed"}
    unknown_times = 0
    for message in messages:
        when = time_value(message.get("created_at"))
        if when is None:
            unknown_times += 1
            continue
        if end is not None and when > end:
            continue
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        rid = message.get("request_id")
        if role == "user" and rid:
            seen_requests.add(rid)
        content = message.get("content")
        stated = (message.get("metadata") or {}).get("stated_choice_id") or {}
        agents = list(stated) or ["default"]
        parts = content if isinstance(content, list) else [content]
        # Save one turn per agent when the stored response has separate parts.
        if role == "user" or len(parts) != len(agents):
            parts, agents = [text_value(content)], ["default"]
        for index, (part, agent) in enumerate(zip(parts, agents)):
            text = text_value(part)
            if not text:
                continue
            turns.append({"turn_id": f"message:{message['_id']}:{index}", "role": role, "text": text,
                          "request_id": rid, "trigger": message.get("trigger"), "agent": agent if role == "assistant" else None,
                          "created_at": stamp(message.get("created_at")), "source": "message",
                          "displayed": (rid, agent) in exposures if row.get("telemetry_available") else None,
                          "stated_choice_id": stated.get(agent) if role == "assistant" else None})
    for request in requests:
        when = time_value(request.get("started_at"))
        rid = request.get("request_id")
        if rid in seen_requests or when is None or (end is not None and when > end) or not request.get("prompt"):
            continue
        turns.append({"turn_id": f"request:{rid}", "role": "user", "text": request["prompt"], "request_id": rid,
                      "trigger": request.get("trigger"), "agent": None, "created_at": stamp(request.get("started_at")),
                      "source": "request_ledger", "displayed": None, "stated_choice_id": None})
    turns.sort(key=lambda t: (t["created_at"], t["role"] != "user", t["turn_id"]))
    suggestions = {}
    references = {}
    clicked = {e.get("data", {}).get("item_id") for e in events if e.get("event_type") == "suggestion_clicked"}
    for event in events:
        data = event.get("data", {})
        if event.get("event_type") == "suggestion_displayed" and data.get("item_id") and data.get("text"):
            suggestions[data["item_id"]] = {"item_id": data["item_id"], "text": data["text"], "clicked": data["item_id"] in clicked}
        if event.get("event_type") == "reference_displayed" and data.get("item_id"):
            references[data["item_id"]] = {"item_id": data["item_id"], "text": data.get("text"), "url": data.get("url"),
                "clicked": any(e.get("event_type") == "reference_clicked" and e.get("data", {}).get("item_id") == data["item_id"] for e in events)}
    packet = {"packet_version": PACKET_VERSION, "participant_id": row["participant_id"], "attempt_id": row["attempt_id"],
              "question_id": row["question_id"], "quiz_id": row["quiz_id"], "question": snapshot or None,
              "answer": {"choice_id": row.get("choice_id"), "correct": row.get("correct"), "answered_at": row.get("answered_at")},
              "turns": turns, "suggestions": sorted(suggestions.values(), key=lambda s: s["item_id"]),
              "references": sorted(references.values(), key=lambda r: r["item_id"]),
              "limitations": [flag for flag, present in (("missing_question_snapshot", not snapshot),
                  ("missing_submission_time", end is None), ("excluded_untimed_messages", unknown_times > 0),
                  ("unsequenced_browser_events", bool(row.get("unsequenced_event_count"))),
                  ("missing_viewport_telemetry", not row.get("telemetry_available"))) if present]}
    packet["packet_hash"] = hashlib.sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    return packet


def conversation_features(packet):
    student = [t for t in packet["turns"] if t["role"] == "user" and t.get("trigger") != "auto_question"]
    assistant = [t for t in packet["turns"] if t["role"] == "assistant"]
    observed = [t for t in assistant if t["displayed"] is True and t.get("stated_choice_id")]
    key = (packet["question"] or {}).get("correct_choice_id")
    comparable = bool(key and observed and "missing_submission_time" not in packet["limitations"])
    wrong = [t for t in observed if t["stated_choice_id"] != key] if comparable else []
    challenges = [t for t in student if CHALLENGE.search(t["text"])]
    specific = [t for t in challenges if SPECIFIC.search(t["text"])]
    prior = {}
    first_wrong = {}
    changes = repairs = regressions = 0
    corrected_after_challenge = False
    for turn in observed:
        agent, choice = turn["agent"], turn["stated_choice_id"]
        previous = prior.get(agent)
        if previous:
            changes += previous["stated_choice_id"] != choice
            if comparable:
                was_wrong = previous["stated_choice_id"] != key
                repairs += was_wrong and choice == key
                regressions += not was_wrong and choice != key
        if comparable and choice != key:
            first_wrong.setdefault(agent, turn["created_at"])
        elif comparable and choice == key and agent in first_wrong:
            corrected_after_challenge |= any(first_wrong[agent] < c["created_at"] < turn["created_at"] for c in challenges)
            first_wrong.pop(agent)
        prior[agent] = turn
    opportunities = sum(any(t["agent"] == earlier["agent"] for earlier in observed[:i]) for i, t in enumerate(observed))
    challenged_wrong = any(w["created_at"] < c["created_at"] for w in wrong for c in challenges)
    dual = {}
    for turn in observed:
        dual.setdefault(turn["request_id"], {})[turn["agent"]] = turn["stated_choice_id"]
    pairs = [(rid, choices) for rid, choices in dual.items() if "A" in choices and "B" in choices]
    disagreements = [rid for rid, choices in pairs if choices["A"] != choices["B"]]
    disagreement_time = min((max(t["created_at"] for t in observed if t["request_id"] == rid) for rid in disagreements), default=None)
    prompts = [re.sub(r"\W+", " ", t["text"].casefold()).strip() for t in student]
    suggestion_verification = [s for s in packet["suggestions"] if VERIFY.search(s["text"])]
    return {
        "conversation_packet_hash": packet["packet_hash"], "student_turns": len(student) if student or assistant else None,
        "student_words": sum(len(t["text"].split()) for t in student) if student else None,
        "reasoning_turns_heuristic": sum(bool(REASONING.search(t["text"])) for t in student) if student else None,
        "specific_challenges_heuristic": len(specific) if student else None,
        "answer_only_turns_heuristic": sum(bool(ANSWER_ONLY.search(t["text"])) for t in student) if student else None,
        "repeated_prompts": len(prompts) - len(set(prompts)) if student else None,
        "mean_ai_response_words": mean(len(t["text"].split()) for t in assistant) if assistant else None,
        "ai_certainty_markers_heuristic": sum(len(CERTAIN.findall(t["text"])) for t in assistant) if assistant else None,
        "ai_recommendation_changes": changes if opportunities else None,
        "ai_wrong_to_correct_transitions": repairs if comparable and opportunities else None,
        "ai_correct_to_wrong_transitions": regressions if comparable and opportunities else None,
        "challenge_after_wrong_ai_heuristic": challenged_wrong if wrong else None,
        "ai_repair_after_challenge_heuristic": corrected_after_challenge if challenged_wrong else None,
        "correct_after_ai_repair": packet["answer"]["correct"] if corrected_after_challenge else None,
        "disagreement_followup_heuristic": any(t["created_at"] > disagreement_time and COMPARE.search(t["text"]) for t in student) if disagreements else None,
        "agents_converged": pairs[-1][1]["A"] == pairs[-1][1]["B"] if len(pairs) > 1 and pairs[0][0] in disagreements else None,
        "verification_suggestions_displayed_heuristic": len(suggestion_verification) if packet["suggestions"] else None,
        "verification_suggestions_clicked_heuristic": sum(s["clicked"] for s in suggestion_verification) if packet["suggestions"] else None,
    }
