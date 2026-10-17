"""Reproducible offline summaries from the administrator's research snapshot ZIP.

No database access. Run with the backend Python environment; mixed models need
requirements-research.txt. Resample participants for descriptive intervals.
These are exploratory analyses, not causal comparisons.
"""
import argparse
import csv
import json
import random
import zipfile
from collections import defaultdict
from pathlib import Path


def interval(values, rng, repetitions=2000):
    if len(values) < 2:
        return None
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(repetitions))
    return [means[int(repetitions * .025)], means[min(repetitions - 1, int(repetitions * .975))]]


def describe(questions, participants, seed=2026, repetitions=2000):
    groups = defaultdict(list)
    for question in questions:
        groups[question["quiz_id"]].append(question)
    rng = random.Random(seed)
    report = {"bootstrap_seed": seed, "bootstrap_repetitions": repetitions,
              "enrolled_participants": len(participants), "participants_with_attempts": len({q["participant_id"] for q in questions}),
              "definitions": ["Accuracy intervals bootstrap participant mean accuracies over graded answers, weighting each participant equally. Missing grades are excluded.",
                "Wrong-AI agreement describes final matching of exposed advice; initial unaided answers were not collected.",
                "Base is always first in the current protocol; base comparisons are confounded with position.",
                "Small pilot intervals and exploratory intent labels are not confirmatory findings."], "variants": {}}
    for variant, rows in sorted(groups.items()):
        people = defaultdict(list)
        for row in rows:
            if row["answered"]:
                people[row["participant_id"]].append(row)
        graded_people = {pid: [r for r in person if isinstance(r.get("correct"), bool)] for pid, person in people.items()}
        accuracies = [sum(r["correct"] is True for r in person) / len(person) for person in graded_people.values() if person]
        wrong = [r for r in rows if r["answered"] and r["wrong_ai_exposed"] is True and r["matched_wrong_ai"] is not None]
        wrong_by_person = defaultdict(list)
        for row in wrong:
            wrong_by_person[row["participant_id"]].append(row)
        agreement = [sum(r["matched_wrong_ai"] is True for r in person) / len(person) for person in wrong_by_person.values()]
        report["variants"][variant] = {
            "participants_assigned": len({r["participant_id"] for r in rows}), "participants_with_answers": len(people),
            "questions_assigned": len(rows), "questions_answered": sum(r["answered"] for r in rows),
            "questions_graded": sum(len(person) for person in graded_people.values()),
            "answers_missing_grade": sum(r["answered"] and r.get("correct") is None for r in rows),
            "participants_with_graded_answers": len(accuracies),
            "participant_mean_accuracy": sum(accuracies) / len(accuracies) if accuracies else None,
            "participant_bootstrap_accuracy_95_interval": interval(accuracies, rng, repetitions),
            "wrong_ai_exposure_questions": len(wrong), "participants_with_wrong_ai_opportunities": len(agreement),
            "participant_mean_wrong_ai_agreement": sum(agreement) / len(agreement) if agreement else None,
            "participant_bootstrap_wrong_ai_agreement_95_interval": interval(agreement, rng, repetitions),
            "telemetry_questions": sum(r["telemetry_available"] for r in rows),
            "quality_flagged_questions": sum(bool(r["quality_flags"]) for r in rows),
            "planned_wrong_ai_questions": sum(r["planned_wrong_ai"] for r in rows),
        }
    report["progress"] = [{"participant_id": p["participant_id"], "completed_steps": p.get("completed_steps", []),
                            "next_unfinished_step": next((s for s in p.get("step_order") or [] if s not in (p.get("completed_steps") or [])), None)} for p in participants]
    return report


def write_csv(path, records):
    if not records:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows([{key: json.dumps(value) if isinstance(value, (list, dict)) else value for key, value in row.items()} for row in records])


def analyze(snapshot, output, seed=2026, repetitions=2000, *, mixed=False, participant_slopes=False, coding_results=()):
    from app.services.research_statistics import paired_comparisons, survey_associations, lexical_clusters, mixed_effects
    with zipfile.ZipFile(snapshot) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("analysis_version") not in ("1.0", "1.1", "1.2", "1.3"):
            raise ValueError("Unsupported analysis version; use the matching analysis script")
        questions = json.loads(archive.read("questions.json"))
        variants = json.loads(archive.read("variants.json"))
        participants = json.loads(archive.read("participants.json"))
        packets = json.loads(archive.read("conversation_packets.json")) if "conversation_packets.json" in archive.namelist() else []
        surveys = json.loads(archive.read("survey_responses.json")) if "survey_responses.json" in archive.namelist() else []
        survey_items = json.loads(archive.read("survey_items_at_export.json")) if "survey_items_at_export.json" in archive.namelist() else []
        annotations = json.loads(archive.read("research_annotations.json")) if "research_annotations.json" in archive.namelist() else []
    from app.schemas.research_coding import ConversationCoding
    from app.services.research_coding import coding_features, validate_evidence, validation_partition, RUBRIC_VERSION
    packets_by_hash = {p["packet_hash"]: p for p in packets}
    for filename in coding_results:
        for line in Path(filename).read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            annotation = json.loads(line)
            if annotation.get("source") not in ("human", "llm") or annotation.get("status") == "failed": continue
            if annotation.get("rubric_version") != RUBRIC_VERSION:
                raise ValueError("Coding rubric version does not match this analyzer")
            packet = packets_by_hash.get(annotation.get("packet_hash"))
            if not packet or any(annotation.get(field) != packet[packet_field] for field, packet_field in
                (("user_id", "participant_id"), ("attempt_id", "attempt_id"), ("question_id", "question_id"))):
                raise ValueError("Coding result does not belong to a current packet")
            validate_evidence(packet, ConversationCoding(labels=annotation["labels"], evidence=annotation.get("evidence", []), notes=annotation.get("notes", "")))
            if annotation["source"] == "human" and (not annotation.get("reviewer_id") or annotation["reviewer_id"] == "REPLACE_WITH_STABLE_REVIEWER_ID"):
                raise ValueError("Completed human reviews require a stable reviewer identifier")
            annotation["partition"] = validation_partition(packet["participant_id"])
            annotations.append(annotation)
    for row in questions:
        records = [a for a in annotations if a.get("attempt_id") == row["attempt_id"] and a.get("question_id") == row["question_id"]]
        if row.get("conversation_packet_hash"):
            row.update(coding_features(records, row["conversation_packet_hash"]))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "questions.csv", questions)
    write_csv(output / "variants.csv", variants)
    report = describe(questions, participants, seed, repetitions)
    report["source_manifest"] = manifest
    report["paired_comparisons"] = paired_comparisons(questions, seed, repetitions)
    report["survey_associations"] = survey_associations(questions, participants, surveys, survey_items, seed, repetitions)
    report["conversation_clusters"] = lexical_clusters(packets)
    from app.services.research_dashboard import comparisons
    report["conversation_metrics"] = comparisons(questions)
    from app.services.research_coding import validation_report
    current_packets = {p["packet_hash"] for p in packets}
    report["coding_validation"] = validation_report([a for a in annotations if a.get("packet_hash") in current_packets])
    if mixed:
        report["mixed_effects"] = [mixed_effects(questions, outcome, seed, participant_slopes) for outcome in ("accuracy", "wrong_ai_agreement")]
    write_csv(output / "paired_comparisons.csv", report["paired_comparisons"]["comparisons"])
    write_csv(output / "survey_associations.csv", report["survey_associations"]["associations"])
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path, default=Path("research-analysis"))
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--bootstrap-repetitions", type=int, default=2000)
    parser.add_argument("--mixed-effects", action="store_true", help="Fit optional Bayesian logistic models; install requirements-research.txt first")
    parser.add_argument("--participant-slopes", action="store_true", help="Include independent participant deviations for rotated conditions in mixed models")
    parser.add_argument("--coding-results", type=Path, action="append", default=[], help="Merge evidence-validated offline human/model JSONL annotations; may repeat")
    args = parser.parse_args()
    if not 100 <= args.bootstrap_repetitions <= 20000:
        parser.error("Use 100 to 20000 bootstrap repetitions")
    analyze(args.snapshot, args.output, args.seed, args.bootstrap_repetitions,
            mixed=args.mixed_effects, participant_slopes=args.participant_slopes, coding_results=args.coding_results)
    print(f"Wrote question CSV, variant CSV and report to {args.output.resolve()}")
