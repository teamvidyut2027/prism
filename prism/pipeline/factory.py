"""The dataset factory.

For every (family, difficulty, index) cell the factory runs a rejection-sampling
funnel and records why each attempt was rejected:

    sample scene ─► ambiguity margins ─► render ─► re-render (determinism)
        ─► pixel verifier recovers facts ─► questions ─► gold == verified answer
        ─► near-duplicate filter ─► variants (paraphrase / perturbation / counterfactual)

Everything is seeded from ``(seed, family, difficulty, index, attempt)``, so a
dataset is a pure function of its config: rebuild it anywhere and you get
byte-identical images and the same questions.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from ..core.render import dhash, hamming, png_bytes, sha256
from ..core.rng import rng
from ..core.spec import AnswerType, Question, Rejected, Task, VariantKind
from ..families import REGISTRY, VerifyError
from ..validate.perturb import KINDS, perturb, recoverable_view
from . import stats as stats_mod

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("PRISM_DATA", ROOT / "data"))


@dataclass
class BuildConfig:
    name: str = "prism-core"
    seed: int = 2026
    families: list[str] = field(default_factory=lambda: list(REGISTRY))
    difficulties: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5])
    per_cell: int = 6                 # base scenes per (family, difficulty)
    questions_per_task: int = 3
    paraphrase: bool = True
    perturb: bool = True
    counterfactual: bool = True
    near_dup_hamming: int = 2         # 256-bit dHash distance at or below which two images count as near-identical
    max_attempts: int = 40
    workers: int = 0                  # 0 = number of CPUs (capped at 8)


def answers_agree(t: AnswerType, a, b) -> bool:
    if t == AnswerType.NUMBER:
        return abs(float(a) - float(b)) < 1e-6
    return a == b


def _short(template: str) -> str:
    return template.split(".", 1)[1]


def _verify(fam, img_arr, manifest, facts) -> tuple[dict | None, list[str]]:
    try:
        measured = fam.measure(img_arr, manifest)
    except VerifyError as e:
        return None, [str(e)]
    return measured, fam.compare_facts(facts, measured)


def generate_cell(family: str, seed: int, d: int, index: int, cfg: dict) -> dict:
    """Generate one base task and its variants. Runs in a worker process."""
    fam = REGISTRY[family]
    ev: Counter = Counter()
    examples: list[str] = []
    tid = f"{family}-d{d}-{index:04d}"
    for attempt in range(cfg["max_attempts"]):
        r = rng(seed, family, d, index, attempt)
        ev["attempts"] += 1
        try:
            scene = fam.sample_scene(r, d)
        except Rejected as e:
            ev["rejected: ambiguous or degenerate scene"] += 1
            if len(examples) < 3:
                examples.append(f"sampling: {e.reason}")
            continue
        facts = fam.facts_from_scene(scene)
        img, man = fam.render(scene)
        if sha256(fam.render(scene)[0]) != sha256(img):
            ev["rejected: non-deterministic render"] += 1
            continue
        measured, problems = _verify(fam, np.asarray(img), man, facts)
        if problems:
            ev["rejected: pixel verifier disagreed with scene"] += 1
            if len(examples) < 3:
                examples.append(f"verifier: {problems[0]}")
            continue
        try:
            qs = fam.build_questions(tid, scene, facts, r, d, cfg["questions_per_task"])
        except Rejected:
            ev["rejected: no unambiguous question"] += 1
            continue
        keep = []
        for q in qs:
            q.verified_answer = fam.answer(_short(q.template), q.params, measured)
            q.verified = answers_agree(q.answer_type, q.answer, q.verified_answer)
            if q.verified:
                keep.append(q)
            else:
                ev["questions dropped: gold != verified answer"] += 1
        if not keep:
            ev["rejected: pixel verifier disagreed with scene"] += 1
            continue
        for i, q in enumerate(keep):
            q.qid = f"{tid}:q{i}"
        ev["accepted"] += 1
        break
    else:
        return {"key": [family, d, index], "tasks": [], "images": {}, "events": dict(ev), "examples": examples}

    W, H = img.size
    base = Task(task_id=tid, family=family, seed=seed, difficulty=d, scene=scene, manifest=man, questions=keep,
                image_id=tid, image_sha256=sha256(img), dhash=dhash(img, 16), width=W, height=H,
                validation={"attempt": attempt, "verifier": "pass", "determinism": "pass",
                            "questions_verified": len(keep),
                            "facts_sha": hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()[:16]})
    tasks, images = [base], {tid: png_bytes(img)}
    vr = rng(seed, family, d, index, "variants")

    # --- paraphrase: same pixels, different wording -----------------------------
    if cfg["paraphrase"]:
        for q in keep:
            n_ph = len(fam.phrasings[_short(q.template)])
            if n_ph > 1:
                ph = (q.phrasing + 1 + vr.randrange(n_ph - 1)) % n_ph
                pq = fam.make_question(f"{tid}-para:q0", _short(q.template), q.params, scene, facts, ph)
                pq.verified_answer, pq.verified = q.verified_answer, True
                tasks.append(Task(task_id=f"{tid}-para", family=family, seed=seed, difficulty=d, scene=scene,
                                  manifest=man, questions=[pq], variant=VariantKind.PARAPHRASE.value,
                                  parent_id=tid, image_id=tid, image_sha256=base.image_sha256, dhash=base.dhash,
                                  width=W, height=H, variant_info={"pairs": {pq.qid: q.qid}},
                                  validation=dict(base.validation)))
                ev["variants: paraphrase"] += 1
                break

    # --- perturbation: same scene, degraded pixels, answer provably recoverable ----
    if cfg["perturb"]:
        kind = vr.choice(KINDS)
        strength = round(0.2 * d, 2)
        pimg = perturb(img, kind, strength, seed, family, d, index)
        pm, problems = _verify(fam, recoverable_view(pimg), man, facts)
        if not problems:
            pqs, pairs = [], {}
            for i, q in enumerate(keep):
                nq = Question.from_dict(q.to_dict())
                nq.qid = f"{tid}-pert:q{i}"
                pairs[nq.qid] = q.qid
                pqs.append(nq)
            pid = f"{tid}-pert"
            tasks.append(Task(task_id=pid, family=family, seed=seed, difficulty=d, scene=scene, manifest=man,
                              questions=pqs, variant=VariantKind.PERTURB.value, parent_id=tid, image_id=pid,
                              image_sha256=sha256(pimg), dhash=dhash(pimg), width=W, height=H,
                              variant_info={"kind": kind, "strength": strength, "pairs": pairs},
                              validation={**base.validation, "recoverable": "pass"}))
            images[pid] = png_bytes(pimg)
            ev["variants: perturbation"] += 1
        else:
            ev["variants dropped: perturbation destroyed the answer"] += 1

    # --- counterfactual: minimal scene edit that flips the gold answer --------------
    if cfg["counterfactual"]:
        order = list(keep)
        vr.shuffle(order)
        found = False
        for q in order:
            if found:
                break
            t = _short(q.template)
            for k in range(60):
                s2 = fam.mutate(scene, rng(seed, family, d, index, "cf", k), q.params if k % 3 else None)
                if s2 is None:
                    continue
                f2 = fam.facts_from_scene(s2)
                try:
                    cands = fam.question_candidates(s2, f2, rng(0), d)
                except Rejected:
                    continue
                if (t, q.params) not in cands:
                    continue                     # the question would be ambiguous on the edited scene
                new_ans = fam.answer(t, q.params, f2)
                if answers_agree(q.answer_type, q.answer, new_ans):
                    continue                     # the edit does not change the answer
                img2, man2 = fam.render(s2)
                m2, problems = _verify(fam, np.asarray(img2), man2, f2)
                if problems:
                    continue
                cq = fam.make_question(f"{tid}-cf:q0", t, q.params, s2, f2, q.phrasing)
                cq.verified_answer = fam.answer(t, q.params, m2)
                cq.verified = answers_agree(cq.answer_type, cq.answer, cq.verified_answer)
                if not cq.verified:
                    continue
                cid = f"{tid}-cf"
                tasks.append(Task(task_id=cid, family=family, seed=seed, difficulty=d, scene=s2, manifest=man2,
                                  questions=[cq], variant=VariantKind.COUNTERFACTUAL.value, parent_id=tid, image_id=cid,
                                  image_sha256=sha256(img2), dhash=dhash(img2), width=img2.size[0], height=img2.size[1],
                                  variant_info={"pairs": {cq.qid: q.qid}, "from": q.answer, "to": cq.answer},
                                  validation={"verifier": "pass", "determinism": "pass", "questions_verified": 1}))
                images[cid] = png_bytes(img2)
                ev["variants: counterfactual"] += 1
                found = True
                break
        if not found:
            ev["variants dropped: no answer-flipping edit found"] += 1

    return {"key": [family, d, index], "tasks": [t.to_dict() for t in tasks], "images": images,
            "events": dict(ev), "examples": examples}


def build_dataset(cfg: BuildConfig, progress: Callable[[int, int, str], None] | None = None) -> dict:
    t0 = time.time()
    out = DATA_DIR / "datasets" / cfg.name
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    jobs = [(f, d, i) for f in cfg.families for d in cfg.difficulties for i in range(cfg.per_cell)]
    cdict = asdict(cfg)
    results: dict[tuple, dict] = {}
    workers = cfg.workers or min(8, os.cpu_count() or 2)
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(generate_cell, f, cfg.seed, d, i, cdict): (f, d, i) for f, d, i in jobs}
            for n, fut in enumerate(as_completed(futs), 1):
                results[futs[fut]] = fut.result()
                if progress:
                    progress(n, len(jobs), "%s d%d" % futs[fut][:2])
    else:
        for n, (f, d, i) in enumerate(jobs, 1):
            results[(f, d, i)] = generate_cell(f, cfg.seed, d, i, cdict)
            if progress:
                progress(n, len(jobs), f"{f} d{d}")

    # deterministic post-pass: near-duplicate filter in a fixed order
    funnel: dict[str, Counter] = defaultdict(Counter)
    examples: dict[str, list] = defaultdict(list)
    seen: dict[str, list[str]] = defaultdict(list)
    seen_facts: set[str] = set()
    tasks: list[dict] = []
    for key in jobs:
        res = results[key]
        fam = key[0]
        funnel[fam].update(res["events"])
        examples[fam].extend(res["examples"][:2])
        if not res["tasks"]:
            funnel[fam]["cells with no accepted task"] += 1
            continue
        base = res["tasks"][0]
        fsha = base["validation"]["facts_sha"]
        if fsha in seen_facts:
            funnel[fam]["rejected: duplicate scene content"] += 1
            funnel[fam]["accepted"] -= 1
            continue
        if any(hamming(base["dhash"], h) <= cfg.near_dup_hamming for h in seen[fam]):
            funnel[fam]["rejected: near-duplicate image"] += 1
            funnel[fam]["accepted"] -= 1
            continue
        seen_facts.add(fsha)
        seen[fam].append(base["dhash"])
        for img_id, data in res["images"].items():
            (out / "images" / f"{img_id}.png").write_bytes(data)
        tasks.extend(res["tasks"])

    with open(out / "tasks.jsonl", "w", encoding="utf-8") as fh:
        for t in tasks:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")
    summary = {
        "name": cfg.name, "config": cdict, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "build_seconds": round(time.time() - t0, 1),
        "funnel": {k: dict(v) for k, v in funnel.items()},
        "rejection_examples": {k: v[:4] for k, v in examples.items()},
        "stats": stats_mod.dataset_stats([Task.from_dict(t) for t in tasks]),
    }
    (out / "dataset.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_card(out, summary)
    return summary


def write_card(out: Path, summary: dict) -> None:
    """A Hugging Face style dataset card."""
    st = summary["stats"]
    lines = [f"# {summary['name']}", "",
             "Synthetic visual-reasoning benchmark generated by **Prism** (Visual Task Factory).", "",
             f"* Tasks: {st['tasks']} ({st['base_tasks']} base scenes + variants)",
             f"* Questions: {st['questions']} (100% gold answers cross-checked against an independent pixel verifier)",
             f"* Families: {', '.join(st['by_family'])}",
             f"* Seed: {summary['config']['seed']}; rebuilding with the same config reproduces identical images.", "",
             "## Files", "* `tasks.jsonl`: one task per line (scene, manifest, questions, gold + verified answers)",
             "* `images/<image_id>.png`", "* `dataset.json`: config, rejection funnel and statistics", ""]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


def list_datasets() -> list[dict]:
    root = DATA_DIR / "datasets"
    out = []
    if root.exists():
        for p in sorted(root.iterdir()):
            meta = p / "dataset.json"
            if meta.exists():
                s = json.loads(meta.read_text(encoding="utf-8"))
                out.append({"name": s["name"], "created": s["created"], "stats": s["stats"]["headline"],
                            "config": s["config"]})
    return out


def load_dataset(name: str) -> tuple[dict, list[Task]]:
    p = DATA_DIR / "datasets" / name
    meta = json.loads((p / "dataset.json").read_text(encoding="utf-8"))
    with open(p / "tasks.jsonl", encoding="utf-8") as fh:
        tasks = [Task.from_dict(json.loads(line)) for line in fh if line.strip()]
    return meta, tasks


def fingerprint(tasks: list[Task]) -> dict:
    """Digest of every image's pixels and every question/answer: equal digests mean identical datasets."""
    h = hashlib.sha256()
    for t in sorted(tasks, key=lambda t: t.task_id):
        h.update(f"{t.task_id}|{t.image_sha256}\n".encode())
        for q in t.questions:
            h.update(f"{q.qid}|{q.text}|{json.dumps(q.answer)}\n".encode())
    return {"tasks": len(tasks), "questions": sum(len(t.questions) for t in tasks),
            "images": len({t.image_id for t in tasks}), "sha256": h.hexdigest()}


def image_path(dataset: str, image_id: str) -> Path:
    return DATA_DIR / "datasets" / dataset / "images" / f"{image_id}.png"
