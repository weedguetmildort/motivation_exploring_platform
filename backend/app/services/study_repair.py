"""Audited, resumable repair of Study 1 journeys created with four quizzes."""
from copy import deepcopy
from datetime import datetime
from . import study_flow as flow
from .result_archive import archive_results


def repair_study1_flow(db, doc):
    if getattr(db, "study_id", None) != "study-1":
        return doc
    uid = str(doc["_id"])
    variants = [key.split(":", 1)[1] for key in (doc.get("step_order") or [])
                if isinstance(key, str) and key.startswith("quiz:") and key.split(":", 1)[1] in flow.all_variants()]
    # An audit record exists only once a repair began, and a begun repair either
    # still has several variants or is stamped repaired. Skip the lookup otherwise;
    # this runs on every Study 1 request.
    if len(variants) <= 1 and doc.get("study1_repair_version") != 1:
        return doc
    history = db["study_flow_repairs"]
    audit = history.find_one({"_id": uid})
    if doc.get("study1_repair_version") == 1 and (not audit or audit.get("finished_at")):
        return doc
    if len(variants) <= 1 and not audit:
        return doc
    assigned = (audit or {}).get("retained_variant") or doc.get("assigned_var")
    if assigned not in flow.all_variants():
        assigned = variants[0] if variants else next(v for v in (doc.get("variant_sequence") or []) if v in flow.all_variants())
    fields = ("step_order", "completed_steps", "variant_sequence", "assigned_var", "quiz_set_assignment",
              "study_protocol", "study_flow_mode", "study_flow_version", "survey_stage",
              "survey_pre_base_completed", "quiz_base_completed", "survey_post_base_completed",
              "quiz_variant_completed", "survey_post_variant_completed")
    history.update_one({"_id": uid}, {"$setOnInsert": {"user_id": uid, "original": deepcopy({k: doc.get(k) for k in fields}),
        "retained_variant": assigned, "reason": "study1_flow_repair", "started_at": datetime.utcnow()}}, upsert=True)
    extra = [v for v in flow.all_variants() if v != assigned]
    archive_results(db, "quiz_attempts", {"user_id": uid, "quiz_id": {"$in": extra}}, "study1_flow_repair")
    archive_results(db, "survey_responses", {"user_id": uid, "stage": {"$in": [flow.post_variant_stage(v) for v in extra]}}, "study1_flow_repair")
    # Preserve the historical survey schedule, not today's settings. The repair
    # only removes the mistakenly assigned variants.
    settings = (doc.get("study_protocol") or {}).get("survey_stages")
    survey_mode = "end_only" if "survey:post_variant" in (doc.get("step_order") or []) else "per_variant"
    order = flow.build_step_order([assigned], settings, survey_mode)
    while True:
        completed = set(doc.get("completed_steps") or [])
        completed.update(flow._legacy_backfill_completed({**doc, "assigned_var": assigned}, order))
        if "survey:post_variant" in completed or doc.get("survey_post_variant_completed"):
            completed.add(flow.survey_response_step({**doc, "step_order": order, "assigned_var": assigned}, "post_variant"))
        completed.update(flow.completed_result_steps(db, {**doc, "assigned_var": assigned}))
        protocol = {**(doc.get("study_protocol") or {}), "mode": flow.MODE_SINGLE_VARIANT, "variant_survey_mode": survey_mode}
        patch = {"step_order": order, "completed_steps": [s for s in order if s in completed],
                 "variant_sequence": [assigned], "assigned_var": assigned, "study_flow_mode": flow.MODE_SINGLE_VARIANT,
                 "study_protocol": protocol, "study1_repair_version": 1, "progress_reconciled_version": 1}
        # Keep the existing mapping (and its historical entries) intact. It is
        # useful evidence and does not schedule additional quizzes.
        patch.update(flow.derive_legacy_flags({**doc, **patch}))
        result = db["users"].update_one({"_id": doc["_id"], "step_order": doc.get("step_order"),
            "completed_steps": doc.get("completed_steps")}, {"$set": patch})
        if result.matched_count:
            history.update_one({"_id": uid}, {"$set": {"finished_at": datetime.utcnow(), "repaired_order": order}})
            return {**doc, **patch}
        doc = db["users"].find_one({"_id": doc["_id"]})
