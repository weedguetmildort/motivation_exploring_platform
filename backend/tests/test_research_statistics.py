import random
import pytest
from app.services.research_statistics import paired_comparisons, survey_associations, lexical_clusters, mixed_effects, spearman


def row(pid, quiz, correct, **extra):
    return {"participant_id": pid, "attempt_id": f"{pid}-{quiz}", "question_id": "q", "question_version": "v1",
        "study_flow_version": 3, "quiz_id": quiz, "answered": True, "correct": correct, "archived": False,
        "attempt_status": "completed", "quality_flags": [], "snapshot_available": True, "variant_position": 2, **extra}


def test_paired_effects_weight_people_and_apply_holm_to_the_reported_family():
    rows = []
    for pid in range(4):
        rows += [row(str(pid), "followup", True), row(str(pid), "links", False)]
    # Unequal question counts cannot make this participant contribute more weight.
    rows += [row("0", "followup", True) for _ in range(9)]
    report = paired_comparisons(rows, repetitions=100)
    comparison = report["comparisons"][0]
    assert comparison["paired_participants"] == 4
    assert comparison["difference"] == 1
    assert comparison["p_exploratory"] == .125 and comparison["p_holm"] == .125
    assert comparison["participant_bootstrap_95_interval"] == [1, 1]
    assert report == paired_comparisons(rows, repetitions=100)


def test_pairing_does_not_mix_protocols_retakes_or_ineligible_wrong_ai():
    rows = [row("a", "followup", True), row("a", "links", False, study_flow_version=4),
            row("b", "followup", True, archived=True), row("b", "links", False),
            row("c", "followup", True, quality_flags=["incomplete_completed_attempt"]), row("c", "links", False)]
    report = paired_comparisons(rows, repetitions=100)
    assert report["comparisons"][0]["paired_participants"] == 0
    assert report["comparisons"][0]["difference"] is None
    assert report["comparisons"][0]["p_holm"] is None
    assert report["excluded_questions"] == 2


def test_sparse_data_has_no_interval_or_test_and_base_is_not_compared():
    report = paired_comparisons([row("a", "base", True), row("a", "links", False), row("a", "followup", True)], repetitions=100)
    assert len(report["comparisons"]) == 1
    assert report["comparisons"][0]["participant_bootstrap_95_interval"] is None
    assert report["comparisons"][0]["p_exploratory"] is None


def test_survey_linkage_reverse_scores_numeric_likert_and_uses_people_once():
    rows = [row("a", "followup", False), row("b", "followup", True), row("b", "followup", False), row("c", "followup", True)]
    surveys = [{"user_id": pid, "stage": "post_followup", "status": "completed", "answers": [{"item_id": "item", "value": value}]} for pid, value in [("a", 1), ("b", 3), ("c", 5)]]
    items = [{"_id": "item", "prompt": "Trust", "type": "likert", "reverse_scored": True, "scale": {"min": 1, "max": 5}}]
    result = survey_associations(rows, [], surveys, items, repetitions=100)["associations"][0]
    assert result["participants"] == 3 and result["spearman_rho"] == -1
    assert spearman([(1, 0), (1, 1), (1, .5)]) is None


def test_survey_associations_use_saved_definitions_after_item_edit_or_deletion():
    saved = {"id": "item", "prompt": "Original", "type": "likert", "reverse_scored": True, "scale": {"min": 1, "max": 5}}
    rows = [row("a", "followup", False), row("b", "followup", True), row("b", "followup", False), row("c", "followup", True)]
    surveys = [{"user_id": pid, "stage": "post_followup", "status": "completed", "item_snapshot": [saved], "answers": [{"item_id": "item", "value": value}]} for pid, value in [("a", 1), ("b", 3), ("c", 5)]]
    result = survey_associations(rows, [], surveys, [], repetitions=10)["associations"][0]
    assert result["item_prompt"] == "Original"
    assert result["spearman_rho"] == -1
    assert result["item_version"]


def test_clusters_are_deterministic_exploratory_and_exclude_auto_prompts():
    packets = [{"participant_id": str(i), "attempt_id": str(i), "question_id": "q", "packet_hash": str(i), "quiz_id": "followup",
        "turns": [{"role": "user", "trigger": "manual", "text": text}]} for i, text in enumerate([
            "denominator fraction division error", "denominator fraction division mistake", "triangle geometry theorem", "why please"])]
    packets.append({**packets[0], "participant_id": "auto", "turns": [{"role": "user", "trigger": "auto_question", "text": "denominator fraction division error"}]})
    result = lexical_clusters(packets)
    assert result["included_conversations"] == 3
    assert result["clusters"][0]["conversations"] == 2
    assert result == lexical_clusters(list(reversed(packets)))


def test_combined_final_survey_is_associated_with_covered_variants_not_first_variant():
    rows = [row(pid, quiz, correct) for pid, correct in [("a", False), ("b", False), ("c", True)] for quiz in ("followup", "double", "links")]
    responses = [{"user_id": pid, "stage": "post_variant", "covered_quiz_ids": ["followup", "double", "links"],
        "status": "completed", "answers": [{"item_id": "item", "value": score}]} for pid, score in [("a", 1), ("b", 3), ("c", 5)]]
    result = survey_associations(rows, [], responses, [{"_id": "item", "type": "likert", "prompt": "Overall"}], repetitions=10)
    assert {item["quiz_id"] for item in result["associations"]} == {"all_variants"}
    assert result["associations"][0]["participants"] == 3


def mixed_rows():
    rng = random.Random(12)
    rows = []
    quizzes = ["double", "followup", "links"]
    for pid in range(12):
        for condition, quiz in enumerate(quizzes):
            for q in range(5):
                rows.append(row(str(pid), quiz, rng.random() < .25 + condition * .15,
                    question_id=f"q{(q + condition * 5 + pid * 5) % 15}", variant_position=2 + (condition + pid) % 3))
    return rows


def test_mixed_model_is_guarded_for_small_or_confounded_data():
    assert mixed_effects([row("a", "followup", True)])["status"] == "insufficient_data"
    pytest.importorskip("statsmodels")
    rows = mixed_rows()
    for value in rows: value["variant_position"] = {"double": 2, "followup": 3, "links": 4}[value["quiz_id"]]
    assert mixed_effects(rows)["status"] == "non_identifiable_design"


def test_optional_mixed_model_fits_crossed_students_and_items_with_reproducible_seed():
    pytest.importorskip("statsmodels")
    result = mixed_effects(mixed_rows(), seed=3)
    assert result["status"] == "fitted", result
    assert result["participants"] == 12
    assert "question" in result["random_effects"] and "participant" in result["random_effects"]
    assert result["coefficients"] == mixed_effects(mixed_rows(), seed=3)["coefficients"]
    assert all("approximate_95_credible_interval_odds_ratio" in value for value in result["coefficients"])
