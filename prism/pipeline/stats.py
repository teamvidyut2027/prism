"""Dataset statistics: coverage, diversity and answer-bias checks.

These are the numbers that answer "is the variation meaningful?":

* coverage of every (family x difficulty) cell and every question template;
* visual diversity, the mean pairwise perceptual-hash distance within a family;
* answer balance: how far the best *blind* strategy gets. ``prior_baseline``
  answers every question with the most common gold answer of its template
  without looking at the image. A benchmark worth running keeps this low.
"""
from __future__ import annotations

import itertools
import math
from collections import Counter, defaultdict

from ..core.render import hamming
from ..core.spec import AnswerType, Task


def _key(a) -> str:
    return "|".join(map(str, a)) if isinstance(a, list) else str(a)


def normalized_entropy(counter: Counter) -> float:
    n = sum(counter.values())
    if n == 0 or len(counter) < 2:
        return 0.0
    h = -sum(c / n * math.log(c / n) for c in counter.values())
    return h / math.log(len(counter))


def dataset_stats(tasks: list[Task]) -> dict:
    base = [t for t in tasks if t.variant == "base"]
    qs = [(t, q) for t in tasks for q in t.questions]
    by_family = Counter(t.family for t in base)
    grid = defaultdict(Counter)
    for t in base:
        grid[t.family][t.difficulty] += 1
    variants = Counter(t.variant for t in tasks if t.variant != "base")
    templates = Counter(q.template for _, q in qs)
    skills = Counter(s for _, q in qs for s in q.skills)
    atypes = Counter(q.answer_type.value for _, q in qs)

    # visual diversity within each family
    diversity = {}
    for fam in by_family:
        hs = [t.dhash for t in base if t.family == fam]
        pairs = list(itertools.combinations(hs, 2))
        if pairs:
            d = [hamming(a, b) for a, b in pairs]
            diversity[fam] = {"mean_dhash_distance": round(sum(d) / len(d), 1), "min_dhash_distance": min(d)}

    # answer balance and the blind prior baseline
    per_t = defaultdict(Counter)
    for _, q in qs:
        per_t[q.template][_key(q.answer)] += 1
    prior_hits = sum(c.most_common(1)[0][1] for c in per_t.values())
    balance = {t: {"distinct_answers": len(c), "majority_share": round(c.most_common(1)[0][1] / sum(c.values()), 3),
                   "entropy": round(normalized_entropy(c), 3)} for t, c in sorted(per_t.items())}
    bools = [q.answer for _, q in qs if q.answer_type == AnswerType.BOOLEAN]
    verified = sum(q.verified for _, q in qs)
    headline = {
        "tasks": len(tasks), "base_tasks": len(base), "questions": len(qs),
        "verified_pct": round(100 * verified / max(1, len(qs)), 1),
        "families": len(by_family), "templates": len(templates),
        "prior_baseline_pct": round(100 * prior_hits / max(1, len(qs)), 1),
        "boolean_true_pct": round(100 * sum(bools) / max(1, len(bools)), 1) if bools else None,
    }
    return {
        "headline": headline, "tasks": len(tasks), "base_tasks": len(base), "questions": len(qs),
        "by_family": dict(by_family), "grid": {k: dict(v) for k, v in grid.items()},
        "variants": dict(variants), "templates": dict(templates), "skills": dict(skills),
        "answer_types": dict(atypes), "diversity": diversity, "answer_balance": balance,
    }
