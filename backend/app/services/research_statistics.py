"""Exploratory, participant-aware analysis; missing evidence stays missing."""
import math
import random
import re
from collections import Counter, defaultdict
from itertools import combinations, product
from statistics import mean

STATISTICS_VERSION = "research-statistics-1"
ROTATED = {"followup", "links", "double"}
PRIMARY = {"accuracy": "correct", "wrong_ai_agreement": "matched_wrong_ai"}


def usable_rows(rows):
    return [r for r in rows if r.get("answered") and r.get("attempt_status") == "completed" and not r.get("archived")
            and "incomplete_completed_attempt" not in r.get("quality_flags", [])]


def quantile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * fraction
    low = int(index); high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (index - low)


def bootstrap_interval(values, rng, repetitions):
    if len(values) < 3:
        return None
    samples = [mean(rng.choices(values, k=len(values))) for _ in range(repetitions)]
    return [quantile(samples, .025), quantile(samples, .975)]


def sign_flip_test(differences, rng, repetitions):
    """Two-sided paired randomization under exchangeable signs; exploratory."""
    if len(differences) < 3:
        return None
    observed = abs(mean(differences))
    n = len(differences)
    if n <= 14:
        samples = [abs(sum(x * sign for x, sign in zip(differences, signs)) / n) for signs in product((-1, 1), repeat=n)]
        return sum(value >= observed - 1e-12 for value in samples) / len(samples)
    extreme = sum(abs(sum(x * rng.choice((-1, 1)) for x in differences) / n) >= observed - 1e-12 for _ in range(repetitions))
    return (extreme + 1) / (repetitions + 1)


def paired_comparisons(rows, seed=2026, repetitions=1000):
    if not 100 <= repetitions <= 20000:
        raise ValueError("Use 100 to 20000 bootstrap repetitions")
    eligible = usable_rows(rows)
    rng = random.Random(seed)
    results = []
    for metric, field in PRIMARY.items():
        groups = defaultdict(list)
        for row in eligible:
            value = row.get(field)
            if row.get("quiz_id") not in ROTATED or not isinstance(value, bool):
                continue
            if metric == "wrong_ai_agreement" and row.get("wrong_ai_exposed") is not True:
                continue
            groups[(row["participant_id"], row.get("study_flow_version"), row["quiz_id"])].append(int(value))
        conditions = sorted({key[2] for key in groups})
        people = sorted({(key[0], key[1]) for key in groups}, key=str)
        for left, right in combinations(conditions, 2):
            # Match protocol versions first, then give each person one difference.
            by_person = defaultdict(list)
            for pid, version in people:
                a, b = groups.get((pid, version, left)), groups.get((pid, version, right))
                if a and b:
                    by_person[pid].append(mean(a) - mean(b))
            differences = [mean(values) for _, values in sorted(by_person.items())]
            results.append({"metric": metric, "left": left, "right": right, "paired_participants": len(differences),
                "difference": mean(differences) if differences else None,
                "participant_bootstrap_95_interval": bootstrap_interval(differences, rng, repetitions),
                "p_exploratory": sign_flip_test(differences, rng, repetitions), "p_holm": None})
    tested = sorted([r for r in results if r["p_exploratory"] is not None], key=lambda r: r["p_exploratory"])
    running = 0
    for rank, result in enumerate(tested):
        running = max(running, min(1, result["p_exploratory"] * (len(tested) - rank)))
        result["p_holm"] = running
    return {"statistics_version": STATISTICS_VERSION, "analysis_status": "exploratory", "seed": seed,
        "bootstrap_repetitions": repetitions, "comparisons": results, "excluded_questions": len(rows) - len(eligible),
        "limitations": ["Differences are left minus right in proportions, averaging paired student differences equally.",
            "Base contrasts are omitted: base is always first, so condition and order cannot be separated reliably.",
            "Retakes, unfinished/incomplete attempts, unknown grades, and ineligible wrong-AI observations are excluded as applicable.",
            "Pairs match protocol version. Sign-flip p-values assume exchangeable signs; Holm correction covers both outcome families shown.",
            "No interval or test is reported for fewer than three paired participants. This is a computation guard, not a power guarantee.",
            "Wrong-AI exposure is observed behavior, not randomized assignment. Conditional comparisons are descriptive, not causal reliance."]}


def ranks(values):
    positions = defaultdict(list)
    for rank, (index, value) in enumerate(sorted(enumerate(values), key=lambda x: x[1]), 1):
        positions[value].append(rank)
    return [mean(positions[value]) for value in values]


def spearman(pairs):
    if len(pairs) < 3:
        return None
    x, y = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    mx, my = mean(x), mean(y)
    scale = math.sqrt(sum((v - mx) ** 2 for v in x) * sum((v - my) ** 2 for v in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / scale if scale else None


def survey_associations(rows, participants, responses, items, seed=2026, repetitions=1000):
    people = {p["participant_id"]: p for p in participants}
    definitions = {str(item["_id"]): item for item in items}
    outcomes = defaultdict(list)
    for row in usable_rows(rows):
        for metric, field in {**PRIMARY, "active_ms": "active_ms", "human_reasoning": "human_coded_reasoning"}.items():
            value = row.get(field)
            if value is not None and (metric != "wrong_ai_agreement" or row.get("wrong_ai_exposed") is True):
                outcomes[(row["participant_id"], row["quiz_id"], metric)].append(float(value))
    groups = defaultdict(dict)
    for response in sorted(responses, key=lambda r: str(r.get("completed_at", ""))):
        if response.get("status") != "completed":
            continue
        pid = response.get("user_id"); stage = response.get("stage", "")
        quiz = "base" if stage == "post_base" else people.get(pid, {}).get("assigned_var") if stage == "post_variant" else stage[5:] if stage.startswith("post_") else None
        if not quiz:
            continue
        for answer in response.get("answers", []):
            item = definitions.get(answer.get("item_id"))
            value = answer.get("value")
            if not item or item.get("type") != "likert" or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                continue
            scale = item.get("scale") or {}
            lo, hi = scale.get("min"), scale.get("max")
            if lo is not None and hi is not None and not lo <= value <= hi:
                continue
            if item.get("reverse_scored"):
                if lo is None or hi is None:
                    continue
                value = lo + hi - value
            for metric in ("accuracy", "wrong_ai_agreement", "active_ms", "human_reasoning"):
                measurements = outcomes.get((pid, quiz, metric))
                if measurements:
                    groups[(quiz, answer["item_id"], metric)][pid] = (value, mean(measurements))
    rng = random.Random(seed)
    results = []
    for (quiz, item_id, metric), by_person in sorted(groups.items()):
        pairs = [pair for _, pair in sorted(by_person.items())]
        coefficient = spearman(pairs)
        samples = [spearman(rng.choices(pairs, k=len(pairs))) for _ in range(repetitions)] if coefficient is not None else []
        samples = [s for s in samples if s is not None]
        results.append({"quiz_id": quiz, "item_id": item_id, "item_prompt": definitions[item_id].get("prompt"), "metric": metric,
                        "participants": len(pairs), "spearman_rho": coefficient,
                        "participant_bootstrap_95_interval": [quantile(samples, .025), quantile(samples, .975)] if len(samples) >= repetitions * .8 else None})
    return {"analysis_status": "exploratory", "associations": results,
            "limitations": "Post-quiz Likert items are associated with same-quiz behavior, one point per participant. Reverse scoring uses exported item definitions. Item edits are not historically frozen. These associations are not causal and do not define a trust scale or validate a construct."}


def lexical_clusters(packets, threshold=.45, limit=500):
    """Deterministic TF-IDF cosine connected components; no external model calls."""
    if not 0 < threshold <= 1 or not 1 <= limit <= 2000:
        raise ValueError("Invalid lexical clustering threshold or limit")
    stop = set("the and that this with have from what which please answer question just you your are was for how why can could would should it is of to in a an i me my".split())
    docs = []
    for packet in sorted(packets, key=lambda p: (p["participant_id"], p["attempt_id"], p["question_id"])):
        text = " ".join(t["text"] for t in packet["turns"] if t["role"] == "user" and t.get("trigger") != "auto_question")
        counts = Counter(token for token in re.findall(r"[^\W\d_]{2,}", text.casefold()) if token not in stop)
        if counts:
            docs.append((packet, counts))
    available = len(docs); docs = docs[:limit]
    frequency = Counter(token for _, counts in docs for token in counts)
    vectors = []
    for _, counts in docs:
        vector = {word: (1 + math.log(count)) * (1 + math.log((1 + len(docs)) / (1 + frequency[word]))) for word, count in counts.items()}
        length = math.sqrt(sum(value ** 2 for value in vector.values()))
        vectors.append({word: value / length for word, value in vector.items()})
    parent = list(range(len(docs)))
    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]; index = parent[index]
        return index
    for left, right in combinations(range(len(docs)), 2):
        similarity = sum(value * vectors[right].get(word, 0) for word, value in vectors[left].items())
        if similarity >= threshold:
            parent[root(right)] = root(left)
    groups = defaultdict(list)
    totals = Counter(p["quiz_id"] for p, _ in docs)
    for index in range(len(docs)):
        groups[root(index)].append(index)
    result = []
    for indexes in groups.values():
        terms = Counter()
        for index in indexes: terms.update(vectors[index])
        conditions = Counter(docs[index][0]["quiz_id"] for index in indexes)
        result.append({"terms": [term for term, _ in sorted(terms.items(), key=lambda pair: (-pair[1], pair[0]))[:8]],
            "conversations": len(indexes), "variant_counts": dict(conditions),
            "variant_document_rates": {quiz: count / totals[quiz] for quiz, count in conditions.items()},
            "members": [{k: docs[index][0][k] for k in ("participant_id", "attempt_id", "question_id", "packet_hash")} for index in indexes]})
    return {"method": "TF-IDF cosine connected components", "exploratory": True, "threshold": threshold, "limit": limit,
            "eligible_conversations": available, "included_conversations": len(docs), "truncated": available > limit,
            "clusters": sorted(result, key=lambda c: (-c["conversations"], c["terms"])),
            "limitations": "Lexical groups need human interpretation and can reflect wording or question topics. They are not validated semantic categories. Missing and auto-generated student text is excluded."}


def mixed_effects(rows, outcome="accuracy", seed=2026, participant_slopes=False):
    """Optional Bayesian logistic GLMM; approximate credible intervals, not p-values."""
    if outcome not in PRIMARY:
        raise ValueError("Unknown mixed-model outcome")
    field = PRIMARY[outcome]
    data = [dict(r, y=int(r[field])) for r in usable_rows(rows) if r.get("quiz_id") in ROTATED
            and isinstance(r.get(field), bool) and r.get("snapshot_available") and r.get("variant_position") is not None
            and r.get("study_flow_version") is not None and r.get("question_version") is not None
            and (outcome != "wrong_ai_agreement" or r.get("wrong_ai_exposed") is True)]
    context = {"outcome": outcome, "included_questions": len(data), "excluded_questions": len(rows) - len(data),
               "participants": len({r["participant_id"] for r in data}), "analysis_status": "exploratory",
               "method": "Bayesian logistic mixed model, mean-field variational approximation",
               "limitations": "Base omitted due to fixed first position. Weakly informative priors and approximate posterior intervals are not frequentist significance tests. Wrong-AI conditional models are descriptive. Random slopes are optional independent participant deviations. Eligibility guards do not establish adequate statistical power."}
    if context["participants"] < 5 or len({r["quiz_id"] for r in data}) < 2 or len({r["y"] for r in data}) < 2:
        return {**context, "status": "insufficient_data"}
    try:
        import numpy as np
        import pandas as pd
        import statsmodels
        from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
    except ImportError:
        return {**context, "status": "dependency_unavailable", "setup": "Install backend/requirements-research.txt in the offline analysis environment"}
    frame = pd.DataFrame(data)
    frame["item"] = frame["question_id"].astype(str) + "@" + frame["question_version"].fillna("legacy").astype(str)
    frame["position_centered"] = frame["variant_position"].astype(float) - frame["variant_position"].astype(float).mean()
    formula = "y ~ C(quiz_id)"
    if frame["position_centered"].nunique() > 1: formula += " + position_centered"
    if frame["study_flow_version"].nunique() > 1: formula += " + C(study_flow_version)"
    random = {"participant": "0 + C(participant_id)", "question": "0 + C(item)"}
    if participant_slopes:
        for index, quiz in enumerate(sorted(frame["quiz_id"].unique())[1:]):
            frame[f"condition_{index}"] = (frame["quiz_id"] == quiz).astype(float)
            random[f"participant_slope_{index}"] = f"0 + C(participant_id):condition_{index}"
    try:
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            model = BinomialBayesMixedGLM.from_formula(formula, random, frame, vcp_p=.5, fe_p=2)
            if np.linalg.matrix_rank(model.exog) < model.exog.shape[1]:
                return {**context, "status": "non_identifiable_design", "formula": formula}
            fit = model.fit_vb(rng=seed, minim_opts={"maxiter": 1000})
        success = bool(fit.optim_retvals.get("success"))
        finite = bool(np.isfinite(fit.fe_mean).all() and np.isfinite(fit.fe_sd).all())
        coefficients = [{"term": name, "log_odds": float(value), "posterior_sd": float(sd),
                         "odds_ratio": math.exp(float(value)),
                         "approximate_95_credible_interval_odds_ratio": [math.exp(float(value - 1.96 * sd)), math.exp(float(value + 1.96 * sd))]}
                        for name, value, sd in zip(model.exog_names, fit.fe_mean, fit.fe_sd)] if success and finite else []
        return {**context, "status": "fitted" if success and finite else "fit_unreliable", "formula": formula,
                "random_effects": random, "priors": {"fixed_effect_sd": 2, "log_random_sd_sd": .5},
                "coefficients": coefficients, "warnings": sorted({str(w.message) for w in caught}),
                "package_versions": {"statsmodels": statsmodels.__version__, "numpy": np.__version__, "pandas": pd.__version__}}
    except Exception as error:
        return {**context, "status": "fit_failed", "error_type": type(error).__name__}
