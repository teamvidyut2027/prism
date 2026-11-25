"""Turn graded responses into a diagnosis of where a model succeeds or struggles."""
from __future__ import annotations

import math
from collections import defaultdict

from ..core.spec import Task


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def cell(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"n": n, "correct": k, "acc": round(k / n, 4) if n else None, "lo": round(lo, 4), "hi": round(hi, 4)}


def _group(rows, keyf) -> dict:
    g = defaultdict(lambda: [0, 0])
    for r in rows:
        for k in keyf(r):
            g[k][0] += r["correct"]
            g[k][1] += 1
    return {k: cell(*v) for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}


def compute_metrics(tasks: list[Task], responses: list[dict], price_in=0.0, price_out=0.0) -> dict:
    tmap = {t.task_id: t for t in tasks}
    qmap = {q.qid: (t, q) for t in tasks for q in t.questions}
    rows = []
    for r in responses:
        if r["qid"] not in qmap:
            continue
        t, q = qmap[r["qid"]]
        rows.append({**r, "family": t.family, "difficulty": t.difficulty, "variant": t.variant,
                     "template": q.template, "skills": q.skills, "atype": q.answer_type.value,
                     "kind": t.variant_info.get("kind")})
    by_qid = {r["qid"]: r for r in rows}
    n, k = len(rows), sum(r["correct"] for r in rows)
    base = [r for r in rows if r["variant"] == "base"]

    out = {
        "overall": {**cell(k, n), "base": cell(sum(r["correct"] for r in base), len(base))},
        "by_family": _group(rows, lambda r: [r["family"]]),
        "by_difficulty": _group(rows, lambda r: [r["difficulty"]]),
        "by_skill": _group(rows, lambda r: r["skills"]),
        "by_answer_type": _group(rows, lambda r: [r["atype"]]),
        "by_template": _group(rows, lambda r: [r["template"]]),
        "by_variant": _group(rows, lambda r: [r["variant"]]),
        "by_perturbation": _group([r for r in rows if r["variant"] == "perturbation"], lambda r: [r["kind"]]),
        "family_difficulty": {f: _group([r for r in rows if r["family"] == f], lambda r: [r["difficulty"]])
                              for f in sorted({r["family"] for r in rows})},
    }

    # --- paired analyses ------------------------------------------------------------
    def pairs(variant):
        for t in tasks:
            if t.variant != variant:
                continue
            for new_q, old_q in t.variant_info.get("pairs", {}).items():
                if new_q in by_qid and old_q in by_qid:
                    yield by_qid[old_q], by_qid[new_q]

    para = list(pairs("paraphrase"))
    pert = list(pairs("perturbation"))
    cf = list(pairs("counterfactual"))
    same = lambda a, b: a["parsed"] is not None and a["parsed"] == b["parsed"]
    base_ok_pert = [p for p in pert if p[0]["correct"]]
    out["consistency"] = {
        "pairs": len(para),
        "same_answer": round(sum(same(a, b) for a, b in para) / len(para), 4) if para else None,
        "both_correct": round(sum(a["correct"] and b["correct"] for a, b in para) / len(para), 4) if para else None,
    }
    out["robustness"] = {
        "pairs": len(pert),
        "clean_acc": round(sum(a["correct"] for a, _ in pert) / len(pert), 4) if pert else None,
        "perturbed_acc": round(sum(b["correct"] for _, b in pert) / len(pert), 4) if pert else None,
        "flip_rate": round(sum(not b["correct"] for _, b in base_ok_pert) / len(base_ok_pert), 4) if base_ok_pert else None,
    }
    out["counterfactual"] = {
        "pairs": len(cf),
        # both right: the model's answer tracked a minimal edit of the scene
        "grounded": round(sum(a["correct"] and b["correct"] for a, b in cf) / len(cf), 4) if cf else None,
        # gave the same answer to both images although the truth changed: answer not grounded in pixels
        "stuck": round(sum(same(a, b) for a, b in cf) / len(cf), 4) if cf else None,
    }

    # --- error magnitudes ------------------------------------------------------------
    errs = defaultdict(list)
    for r in rows:
        if r["err"] is not None and r["atype"] in ("integer", "number", "time"):
            errs[r["template"]].append(r["err"])
    out["error_magnitude"] = {t: {"mean": round(sum(v) / len(v), 3), "median": sorted(v)[len(v) // 2],
                                  "max": max(v), "n": len(v)} for t, v in sorted(errs.items())}

    # --- calibration ---------------------------------------------------------------------
    conf = [(r["confidence"], r["correct"]) for r in rows if r["confidence"] is not None]
    if conf:
        bins = defaultdict(list)
        for c, ok in conf:
            bins[min(9, int(c * 10))].append((c, ok))
        ece = sum(len(b) / len(conf) * abs(sum(c for c, _ in b) / len(b) - sum(o for _, o in b) / len(b))
                  for b in bins.values())
        out["calibration"] = {
            "n": len(conf), "ece": round(ece, 4),
            "brier": round(sum((c - o) ** 2 for c, o in conf) / len(conf), 4),
            "mean_confidence": round(sum(c for c, _ in conf) / len(conf), 4),
            "bins": [{"bin": b / 10, "n": len(v), "conf": round(sum(c for c, _ in v) / len(v), 3),
                      "acc": round(sum(o for _, o in v) / len(v), 3)} for b, v in sorted(bins.items())],
        }
    # --- cost & latency --------------------------------------------------------------------
    lat = sorted(r["latency_ms"] for r in rows if r["latency_ms"] and not r["cached"])
    tin, tout = sum(r["in_tok"] or 0 for r in rows), sum(r["out_tok"] or 0 for r in rows)
    out["usage"] = {
        "input_tokens": tin, "output_tokens": tout,
        "cost_usd": round(tin / 1e6 * price_in + tout / 1e6 * price_out, 4),
        "latency_p50_ms": round(lat[len(lat) // 2]) if lat else None,
        "latency_p95_ms": round(lat[int(len(lat) * 0.95) - 1]) if lat else None,
        "errors": sum(1 for r in rows if r["note"] and r["note"].startswith("error")),
        "cached": sum(1 for r in rows if r["cached"]),
    }
    return out
