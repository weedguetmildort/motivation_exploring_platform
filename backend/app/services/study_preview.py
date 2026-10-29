"""Build current admin previews without consuming enrollment assignment slots."""
from dataclasses import replace

from . import study_flow as flow


def preview_quiz_sets(config, order, stored):
    """The sets an admin preview draws from, chosen the way participants' are.

    Preset studies follow the current map, so an unmapped quiz draws from the
    whole pool exactly as a participant's would. Random modes keep the admin's
    existing distinct sets, otherwise draw a fresh random spread; a preview
    never claims a balanced-random slot.
    """
    quiz_ids = flow.quiz_ids_in_order(order)
    if config.quiz_set_mode == flow.QUIZ_SET_MODE_PRESET:
        return flow.resolve_quiz_set_assignment(config, quiz_ids)
    covered = quiz_ids[:len(flow.ALL_SET_IDS)]
    kept = {quiz_id: stored[quiz_id] for quiz_id in covered if quiz_id in (stored or {})}
    if len(kept) == len(covered) and len(set(kept.values())) == len(kept):
        return kept
    return flow.resolve_quiz_set_assignment(replace(config, quiz_set_mode=flow.QUIZ_SET_MODE_RANDOM), quiz_ids)


def admin_preview_fields(db, doc):
    config = flow.load_study_config(db)
    sequence = list(config.variant_order)
    if config.mode == flow.MODE_SINGLE_VARIANT:
        sequence = [doc["assigned_var"]] if doc.get("assigned_var") in flow.all_variants() else sequence[:1]
    order = flow.build_step_order(sequence, config.survey_stages, config.variant_survey_mode)
    protocol = config.as_dict()
    if getattr(db, "study_id", None) == "study-2":
        from .studies import policy_protocol_fields
        protocol.update(policy_protocol_fields())
    patch = {"step_order": order, "study_protocol": protocol, "study_flow_version": config.version,
             "study_flow_mode": config.mode, "variant_sequence": sequence, "assigned_var": sequence[0],
             "completed_steps": [step for step in (doc.get("completed_steps") or []) if step in order],
             "quiz_set_assignment": preview_quiz_sets(config, order, doc.get("quiz_set_assignment"))}
    patch.update(flow.derive_legacy_flags({**doc, **patch}))
    return patch


def refresh_admin_preview(db, doc):
    patch = admin_preview_fields(db, doc)
    if any(doc.get(key) != value for key, value in patch.items()):
        db["users"].update_one({"_id": doc["_id"]}, {"$set": patch})
    return {**doc, **patch}
