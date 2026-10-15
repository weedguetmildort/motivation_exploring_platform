"""Reproducible offline summaries from the administrator's research snapshot ZIP.

No database access or third-party packages. Resample participants, not individual
questions, for descriptive bootstrap intervals. These are not causal comparisons.
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


def analyze(snapshot, output, seed=2026, repetitions=2000):
    with zipfile.ZipFile(snapshot) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("analysis_version") not in ("1.0", "1.1"):
            raise ValueError("Unsupported analysis version; use the matching analysis script")
        questions = json.loads(archive.read("questions.json"))
        variants = json.loads(archive.read("variants.json"))
        participants = json.loads(archive.read("participants.json"))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "questions.csv", questions)
    write_csv(output / "variants.csv", variants)
    report = describe(questions, participants, seed, repetitions)
    report["source_manifest"] = manifest
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path, default=Path("research-analysis"))
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--bootstrap-repetitions", type=int, default=2000)
    args = parser.parse_args()
    if args.bootstrap_repetitions < 100:
        parser.error("Use at least 100 bootstrap repetitions")
    analyze(args.snapshot, args.output, args.seed, args.bootstrap_repetitions)
    print(f"Wrote question CSV, variant CSV and report to {args.output.resolve()}")
