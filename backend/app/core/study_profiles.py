"""Study identity and enrollment defaults, independent of database services."""

PROFILES = {
    "study-1": {"mode": "single_variant", "questions_per_quiz": 10, "quiz_set_mode": "preset", "variant_survey_mode": "end_only"},
    "study-2": {"mode": "all_variants", "questions_per_quiz": 5, "quiz_set_mode": "balanced_random", "variant_survey_mode": "per_variant"},
}
STUDY_IDS = tuple(PROFILES)


def study_id_of(db, default=None):
    """The study a database handle is scoped to; unscoped handles (and test mocks) get ``default``."""
    study_id = getattr(db, "study_id", None)
    return study_id if isinstance(study_id, str) else default


def profile_for(db):
    return PROFILES.get(study_id_of(db), {})
