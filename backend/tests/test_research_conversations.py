from datetime import datetime, timedelta
from app.services.research_conversations import build_packet, conversation_features

NOW = datetime(2026, 1, 1)


def message(identifier, role, text, seconds, **extra):
    return {"_id": identifier, "role": role, "content": text, "created_at": NOW + timedelta(seconds=seconds), **extra}


def packet(messages, requests=(), events=(), **extra):
    row = {"participant_id": "u", "attempt_id": "a", "question_id": "q", "quiz_id": "followup",
           "answered_at": (NOW + timedelta(seconds=10)).isoformat(), "choice_id": "a", "correct": True,
           "telemetry_available": True, **extra}
    return build_packet(row, {"correct_choice_id": "a"}, messages, requests, events)


def exposed(request, agent="default"):
    return {"event_type": "ai_message_displayed", "data": {"request_id": request, "agent": agent}}


def test_observed_wrong_challenge_correction_sequence_is_auditable():
    messages = [message("m1", "assistant", "Definitely B", 1, request_id="r1", metadata={"stated_choice_id": {"default": "b"}}),
                message("m2", "user", "That denominator is wrong because 2+2=4", 2, request_id="r2", trigger="manual"),
                message("m3", "assistant", "Correction: A", 3, request_id="r2", metadata={"stated_choice_id": {"default": "a"}})]
    value = packet(messages, events=[exposed("r1"), exposed("r2")])
    features = conversation_features(value)
    assert features["ai_wrong_to_correct_transitions"] == 1
    assert features["specific_challenges_heuristic"] == 1
    assert features["ai_repair_after_challenge_heuristic"] is True
    assert features["correct_after_ai_repair"] is True
    assert value["turns"][1]["turn_id"] == "message:m2:0"
    assert value["packet_hash"] == packet(list(reversed(messages)), events=[exposed("r2"), exposed("r1")])["packet_hash"]


def test_unshown_or_post_submission_replies_cannot_count_as_ai_repair():
    messages = [message("m1", "assistant", "B", 1, request_id="r1", metadata={"stated_choice_id": {"default": "b"}}),
                message("m2", "user", "Are you sure?", 2, trigger="manual"),
                message("m3", "assistant", "A", 11, request_id="r2", metadata={"stated_choice_id": {"default": "a"}})]
    value = packet(messages, events=[exposed("r1"), exposed("r2")])
    assert len(value["turns"]) == 2
    assert conversation_features(value)["ai_repair_after_challenge_heuristic"] is False
    assert conversation_features(packet(messages, events=[]))["challenge_after_wrong_ai_heuristic"] is None


def test_request_ledger_recovers_missing_user_message_without_duplicates():
    request = {"request_id": "r", "started_at": NOW, "prompt": "Please explain", "trigger": "manual"}
    value = packet([], [request])
    assert value["turns"][0]["source"] == "request_ledger"
    messages = [message("m", "user", "Please explain", 0, request_id="r", trigger="manual")]
    assert len(packet(messages, [request])["turns"]) == 1


def test_unknown_times_are_excluded_and_missing_data_remains_unknown():
    value = packet([{"_id": "m", "role": "user", "content": "I calculated 2+2=4"}])
    assert value["turns"] == [] and "excluded_untimed_messages" in value["limitations"]
    assert conversation_features(value)["reasoning_turns_heuristic"] is None


def test_double_agent_changes_are_compared_within_agent():
    messages = [message("m", "assistant", ["A", "B"], 1, request_id="r", metadata={"stated_choice_id": {"A": "a", "B": "b"}}),
                message("n", "assistant", ["A", "A"], 3, request_id="s", metadata={"stated_choice_id": {"A": "a", "B": "a"}})]
    value = packet(messages, events=[exposed(r, a) for r in ("r", "s") for a in ("A", "B")])
    features = conversation_features(value)
    assert features["agents_converged"] is True and features["ai_recommendation_changes"] == 1
    assert features["ai_wrong_to_correct_transitions"] == 1
