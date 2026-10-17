"""Build current admin previews without consuming enrollment assignment slots."""
from . import study_flow as flow


def admin_preview_fields(db, doc):
    config = flow.load_study_config(db)
    sequence = list(config.variant_order)
    if config.mode == flow.MODE_SINGLE_VARIANT:
        sequence = [doc["assigned_var"]] if doc.get("assigned_var") in flow.all_variants() else sequence[:1]
    order = flow.build_step_order(sequence, config.survey_stages)
    patch = {"step_order": order, "study_protocol": config.as_dict(), "study_flow_version": config.version,
             "study_flow_mode": config.mode, "variant_sequence": sequence, "assigned_var": sequence[0],
             "completed_steps": [step for step in (doc.get("completed_steps") or []) if step in order],
             "quiz_set_assignment": {**dict(zip(flow.quiz_ids_in_order(order), ("a", "b", "c", "d"))),
                                     **(doc.get("quiz_set_assignment") or {})}}
    patch.update(flow.derive_legacy_flags({**doc, **patch}))
    return patch


def refresh_admin_preview(db, doc):
    patch = admin_preview_fields(db, doc)
    if any(doc.get(key) != value for key, value in patch.items()):
        db["users"].update_one({"_id": doc["_id"]}, {"$set": patch})
    return {**doc, **patch}
