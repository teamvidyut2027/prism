"""Audit of the validation machinery itself.

A verifier that always says "agree" would make every dataset look perfect, so
the audit measures two things:

1. **Agreement**: on fresh scenes, how often the pixel verifier recovers
   exactly the facts the generator drew. Disagreements and unreadable scenes
   are the cases the factory rejects.
2. **Sensitivity (label-corruption test)**: we render a minimally *edited*
   scene but keep the *original* facts as the claimed labels, which is what a
   generator bug or a wrong annotation looks like. A useful verifier must flag
   these. We report the share of corruptions caught.

It also re-renders every scene to confirm byte-identical output (determinism)
and checks which perturbations keep the answer recoverable.
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

from ..core.render import sha256
from ..core.rng import rng
from ..core.spec import Rejected
from ..families import REGISTRY, VerifyError
from .perturb import KINDS, perturb, recoverable_view


def _check(fam, arr, man, facts):
    try:
        return fam.compare_facts(facts, fam.measure(arr, man))
    except VerifyError as e:
        return [f"unreadable: {e}"]


def audit_cell(family: str, d: int, n: int, seed: int) -> dict:
    fam = REGISTRY[family]
    c: Counter = Counter()
    examples = []
    for i in range(n):
        r = rng(seed, "audit", family, d, i)
        try:
            scene = fam.sample_scene(r, d)
        except Rejected:
            c["sampling_rejected"] += 1
            continue
        c["scenes"] += 1
        facts = fam.facts_from_scene(scene)
        img, man = fam.render(scene)
        c["deterministic"] += sha256(fam.render(scene)[0]) == sha256(img)
        probs = _check(fam, np.asarray(img), man, facts)
        if probs:
            c["disagree"] += 1
            if len(examples) < 2:
                examples.append(probs[0])
        else:
            c["agree"] += 1
        # label-corruption test: image of an edited scene, labels of the original
        for k in range(10):
            s2 = fam.mutate(scene, rng(seed, "audit-mut", family, d, i, k))
            if s2 is None:
                continue
            f2 = fam.facts_from_scene(s2)
            if f2 == facts:
                continue
            img2, man2 = fam.render(s2)
            c["corruptions"] += 1
            if _check(fam, np.asarray(img2), man2, facts):
                c["corruptions_caught"] += 1
            break
        # perturbation recoverability
        kind = KINDS[i % len(KINDS)]
        c[f"perturb_{kind}_tried"] += 1
        if not _check(fam, recoverable_view(perturb(img, kind, 0.2 * d, seed, family, d, i)), man, facts):
            c[f"perturb_{kind}_recovered"] += 1
    return {"family": family, "difficulty": d, "counts": dict(c), "examples": examples}


def audit(n_per_cell: int = 40, seed: int = 99, progress=None) -> dict:
    jobs = [(f, d) for f in REGISTRY for d in range(1, 6)]
    res = []
    with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as ex:
        futs = [ex.submit(audit_cell, f, d, n_per_cell, seed) for f, d in jobs]
        for k, fut in enumerate(as_completed(futs), 1):
            res.append(fut.result())
            if progress:
                progress(k, len(jobs), f"{res[-1]['family']} d{res[-1]['difficulty']}")
    res.sort(key=lambda x: (x["family"], x["difficulty"]))
    fam_tot: dict[str, Counter] = defaultdict(Counter)
    for x in res:
        fam_tot[x["family"]].update(x["counts"])
    pct = lambda a, b: round(100 * a / b, 2) if b else None
    per_family = {}
    for f, c in fam_tot.items():
        per_family[f] = {
            "scenes": c["scenes"], "agreement_pct": pct(c["agree"], c["scenes"]),
            "determinism_pct": pct(c["deterministic"], c["scenes"]),
            "corruptions": c["corruptions"], "corruption_detection_pct": pct(c["corruptions_caught"], c["corruptions"]),
            "perturbation_recovery_pct": {k: pct(c[f"perturb_{k}_recovered"], c[f"perturb_{k}_tried"]) for k in KINDS},
        }
    T = sum(fam_tot.values(), Counter())
    summary = {
        "scenes": T["scenes"], "agreement_pct": pct(T["agree"], T["scenes"]),
        "determinism_pct": pct(T["deterministic"], T["scenes"]),
        "corruptions": T["corruptions"], "corruption_detection_pct": pct(T["corruptions_caught"], T["corruptions"]),
        "per_family": per_family,
    }
    return {"summary": summary, "cells": res}
