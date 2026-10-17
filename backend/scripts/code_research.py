"""Prepare blinded review packets or explicitly run bounded, resumable model coding.

From backend: python -m scripts.code_research snapshot.zip --output reviews.jsonl
Add --method llm to send text to the configured evaluator; it requires the
existing UF_OPENAI_API_KEY and a separate RESEARCH_EVALUATOR_MODEL environment
variable. No calls are made in the default prepare mode. No database is changed.
Merge completed output into analysis with --coding-results reviews.jsonl.
"""
import argparse
import asyncio
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from app.services.research_coding import RUBRIC_VERSION, rubric_public, validation_partition, model_input, generate_coding, evaluator_status


async def code_snapshot(snapshot, output, method="prepare", limit=20, partition="all"):
    if method not in ("prepare", "llm") or not 1 <= limit <= 10000:
        raise ValueError("Choose prepare/llm and a limit between 1 and 10000")
    with zipfile.ZipFile(snapshot) as archive:
        packets = json.loads(archive.read("conversation_packets.json"))
        annotations = json.loads(archive.read("research_annotations.json")) if "research_annotations.json" in archive.namelist() else []
    output = Path(output)
    existing = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line.strip()] if output.exists() else []
    model = evaluator_status()["model"] if method == "llm" else None
    if method == "llm" and not evaluator_status()["enabled"]:
        raise ValueError(evaluator_status()["reason"])
    source = "llm" if method == "llm" else "human_template"
    completed = {(r.get("packet_hash"), r.get("rubric_version"), r.get("source"), r.get("model"))
                 for r in existing + annotations if r.get("status") != "failed"}
    result = {"written": 0, "skipped": 0, "failed": 0, "method": method}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as stream:
        for packet in sorted(packets, key=lambda p: (p["participant_id"], p["attempt_id"], p["question_id"])):
            if result["written"] + result["failed"] >= limit:
                break
            identity = (packet["packet_hash"], RUBRIC_VERSION, source, model)
            if identity in completed or not packet["answer"].get("answered_at") or (partition != "all" and validation_partition(packet["participant_id"]) != partition):
                result["skipped"] += 1; continue
            # Refuse edited packets rather than evaluating a different transcript under an old ID.
            material = {k: v for k, v in packet.items() if k != "packet_hash"}
            expected = hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
            if packet.get("packet_version") not in ("1", "2") or packet["packet_hash"] != expected:
                raise ValueError("Packet version or content hash is invalid")
            record = {"_id": f"offline:{packet['packet_hash']}:{method}", "user_id": packet["participant_id"],
                "attempt_id": packet["attempt_id"], "question_id": packet["question_id"], "packet_hash": packet["packet_hash"],
                "rubric_version": RUBRIC_VERSION, "source": source, "model": model,
                "partition": validation_partition(packet["participant_id"]), "created_at": datetime.now(timezone.utc).isoformat()}
            try:
                if method == "prepare":
                    record.update(blinded_packet=model_input(packet), rubric=rubric_public(), reviewer_id="REPLACE_WITH_STABLE_REVIEWER_ID",
                        independent_review=False, labels={d["key"]: "insufficient_evidence" for d in rubric_public()}, evidence=[], notes="",
                        instructions="Fill labels and exact quotes, set source to human, use your stable reviewer ID, and attest independent_review only if coded before viewing other labels. Keep packet hash unchanged.")
                else:
                    coding, _, metadata = await generate_coding(packet)
                    record.update(coding.model_dump(), metadata=metadata, reviewer_id=None, independent_review=False)
                result["written"] += 1; completed.add(identity)
            except Exception as error:
                record.update(status="failed", error_type=type(error).__name__)
                result["failed"] += 1
            stream.write(json.dumps(record, ensure_ascii=False) + "\n"); stream.flush()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--method", choices=("prepare", "llm"), default="prepare")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--partition", choices=("all", "development", "validation"), default="all")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(code_snapshot(args.snapshot, args.output, args.method, args.limit, args.partition))))
