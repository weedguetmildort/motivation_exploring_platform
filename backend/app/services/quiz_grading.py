"""Read historical grades without consulting today's editable question bank."""


def answer_correctness(answer, snapshot=None):
    if not answer.get("answered_at"):
        return None
    grade = answer.get("marked_correct")
    if isinstance(grade, bool):
        return grade
    # An immutable attempt snapshot is safe evidence for an absent grade.
    # Missing historical keys remain unknown, rather than becoming incorrect.
    key = (snapshot or {}).get("correct_choice_id")
    choice = answer.get("choice_id")
    return choice == key if key and choice else None
