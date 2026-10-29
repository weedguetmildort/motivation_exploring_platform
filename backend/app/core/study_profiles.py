"""Study identity and enrollment defaults, independent of database services."""

PROFILES = {
    "study-1": {"mode": "single_variant", "questions_per_quiz": 10, "quiz_set_mode": "preset", "variant_survey_mode": "end_only"},
    "study-2": {"mode": "all_variants", "questions_per_quiz": 5, "quiz_set_mode": "balanced_random", "variant_survey_mode": "per_variant"},
}
STUDY_IDS = tuple(PROFILES)


def profile_for(db):
    study_id = getattr(db, "study_id", None)
    return PROFILES.get(study_id, {}) if isinstance(study_id, str) else {}
