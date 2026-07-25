"""Unit tests for scripts/seed_questions.py — the balanced question-bank
generator. Pure (no DB): they exercise the allocator marginals, choice
integrity, determinism, and the computed correctness of the templates."""
import re
import random
from collections import Counter
from math import comb, factorial, perm

import pytest

from scripts.seed_questions import build_bank, TOPICS, SETS, TEMPLATES, _frac, _num


BANK = build_bank(0)


def _correct_label(q) -> str:
    return next(c["label"] for c in q["choices"] if c["id"] == q["correct_choice_id"])


# ── Balancing marginals ──────────────────────────────────────────────────────

class TestMarginals:
    def test_total_is_100(self):
        assert len(BANK) == 100

    def test_20_per_set(self):
        c = Counter(str(q["set"]) for q in BANK)
        assert c == Counter({"a": 20, "b": 20, "c": 20, "d": 20, "None": 20})

    def test_20_per_topic(self):
        assert Counter(q["stem"] for q in BANK) == Counter({t: 20 for t in TOPICS})

    def test_4_per_set_topic_cell(self):
        c = Counter((str(q["set"]), q["stem"]) for q in BANK)
        assert len(c) == 25
        assert set(c.values()) == {4}

    def test_difficulty_spread_34_33_33(self):
        c = Counter(q["difficulty"] for q in BANK)
        assert (c["easy"], c["medium"], c["hard"]) == (34, 33, 33)


# ── Choice integrity ─────────────────────────────────────────────────────────

class TestChoiceIntegrity:
    def test_four_unique_ids(self):
        for q in BANK:
            ids = [c["id"] for c in q["choices"]]
            assert sorted(ids) == ["a", "b", "c", "d"]

    def test_four_unique_labels(self):
        for q in BANK:
            labels = [c["label"] for c in q["choices"]]
            assert len(set(labels)) == 4, q["subtitle"]

    def test_correct_choice_id_is_a_real_option(self):
        for q in BANK:
            assert q["correct_choice_id"] in {c["id"] for c in q["choices"]}

    def test_correct_position_not_biased(self):
        # Every position is used as the key somewhere → not positionally biased
        # (a constant key would masquerade as an anomaly in analytics).
        assert {q["correct_choice_id"] for q in BANK} == {"a", "b", "c", "d"}


# ── Metadata for Phase-8 / Phase-11 compatibility ───────────────────────────

class TestMetadata:
    def test_manual_difficulty_source_keeps_ai_judge_off(self):
        assert all(q["difficulty_source"] == "manual" for q in BANK)
        assert all(q["difficulty_checked"] is True for q in BANK)

    def test_all_active(self):
        assert all(q["active"] for q in BANK)

    def test_sets_use_lowercase_letters_or_none(self):
        assert {str(q["set"]) for q in BANK} == {"a", "b", "c", "d", "None"}


# ── Determinism ──────────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_seed_same_bank(self):
        assert build_bank(0) == build_bank(0)

    def test_different_seed_differs(self):
        assert build_bank(0) != build_bank(7)


# ── Formatting helpers ───────────────────────────────────────────────────────

class TestHelpers:
    def test_frac_reduces_and_collapses_integers(self):
        assert _frac(2, 4) == "1/2"
        assert _frac(3, 6) == "1/2"
        assert _frac(6, 3) == "2"
        assert _frac(0, 5) == "0"

    def test_num_drops_trailing_zero(self):
        assert _num(4.0) == "4"
        assert _num(1.2) == "1.2"


# ── The correct answer is actually correct (recompute independently) ─────────

class TestComputedCorrectness:
    def test_basic_probability_medium(self):
        rng = random.Random("bp-med")
        text, choices, cid = TEMPLATES["Basic Probability"]["medium"](rng)
        s = int(re.search(r"sum is (\d+)", text).group(1))
        ways = 6 - abs(7 - s)
        got = next(c["label"] for c in choices if c["id"] == cid)
        assert got == _frac(ways, 36)

    def test_permutations_medium(self):
        rng = random.Random("pm-med")
        text, choices, cid = TEMPLATES["Permutations"]["medium"](rng)
        n = int(re.search(r"club has (\d+) members", text).group(1))
        got = next(c["label"] for c in choices if c["id"] == cid)
        assert got == str(perm(n, 2))

    def test_combinations_easy(self):
        rng = random.Random("cm-easy")
        text, choices, cid = TEMPLATES["Combinations"]["easy"](rng)
        k, n = map(int, re.search(r"(\d+) students be chosen from a group of (\d+)", text).groups())
        got = next(c["label"] for c in choices if c["id"] == cid)
        assert got == str(comb(n, k))

    def test_permutations_hard_circular(self):
        rng = random.Random("pm-hard")
        text, choices, cid = TEMPLATES["Permutations"]["hard"](rng)
        n = int(re.search(r"can (\d+) people be seated", text).group(1))
        got = next(c["label"] for c in choices if c["id"] == cid)
        assert got == str(factorial(n - 1))

    def test_statistics_easy_mean(self):
        rng = random.Random("st-easy")
        text, choices, cid = TEMPLATES["Statistics"]["easy"](rng)
        nums = [int(x) for x in re.findall(r"-?\d+", text.split("set")[1])]
        got = next(c["label"] for c in choices if c["id"] == cid)
        assert got == str(sum(nums) // len(nums))  # mean is integer by construction

    @pytest.mark.parametrize("topic", TOPICS)
    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
    def test_every_template_runs_and_is_well_formed(self, topic, difficulty):
        # 20 seeds per (topic, difficulty): no exceptions, always 4 options with
        # exactly one correct, and no degenerate/empty labels.
        for i in range(20):
            rng = random.Random(f"{topic}:{difficulty}:{i}")
            text, choices, cid = TEMPLATES[topic][difficulty](rng)
            assert text and len(choices) == 4
            assert cid in {c["id"] for c in choices}
            assert all(c["label"] != "" for c in choices)
