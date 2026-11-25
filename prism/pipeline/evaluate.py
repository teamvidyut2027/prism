"""Evaluation runner: send items to a model concurrently, grade, store, summarise."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Callable

from .. import store
from ..core.rng import derive_seed
from ..grading.grader import grade
from ..models import EvalItem, build_prompt, get_adapter
from .factory import image_path, load_dataset
from .metrics import compute_metrics


def select_items(dataset: str, base_per_family: int | None = None, families: list[str] | None = None,
                 variants: bool = True, seed: int = 0) -> tuple[list, list[EvalItem]]:
    """Deterministic, stratified subset: N base scenes per family (spread over difficulties)
    plus all of their variants, so paired analyses stay complete."""
    meta, tasks = load_dataset(dataset)
    if families:
        tasks = [t for t in tasks if t.family in families]
    chosen = None
    if base_per_family:
        chosen = set()
        for fam in sorted({t.family for t in tasks}):
            base = [t for t in tasks if t.family == fam and t.variant == "base"]
            by_d: dict[int, list] = {}
            for t in sorted(base, key=lambda t: derive_seed(seed, t.task_id)):
                by_d.setdefault(t.difficulty, []).append(t)
            picked, i = [], 0
            while len(picked) < min(base_per_family, len(base)):   # round-robin across difficulty levels
                for d in sorted(by_d):
                    if i < len(by_d[d]) and len(picked) < base_per_family:
                        picked.append(by_d[d][i])
                i += 1
            chosen |= {t.task_id for t in picked}
    sel = [t for t in tasks if (chosen is None or (t.task_id if t.variant == "base" else t.parent_id) in chosen)
           and (variants or t.variant == "base")]
    items, cache = [], {}
    for t in sel:
        if t.image_id not in cache:
            cache[t.image_id] = image_path(dataset, t.image_id).read_bytes()
        for q in t.questions:
            items.append(EvalItem(task=t, question=q, image_png=cache[t.image_id], prompt=build_prompt(q)))
    return sel, items


async def _run(adapter, items, run_id, concurrency, progress, use_cache=True):
    sem = asyncio.Semaphore(concurrency)
    done = 0
    buf: list[dict] = []
    lock = asyncio.Lock()

    async def one(it: EvalItem):
        nonlocal done
        key = hashlib.sha256(f"{adapter.id}|{it.task.image_sha256}|{it.prompt}".encode()).hexdigest()
        cached = store.cache_get(key) if (use_cache and not adapter.blind and adapter.kind == "vlm") else None
        if cached is None:
            async with sem:
                resp = await adapter.answer(it)
            payload = {"raw": resp.raw, "confidence": resp.confidence, "latency_ms": resp.latency_ms,
                       "in_tok": resp.input_tokens, "out_tok": resp.output_tokens, "error": resp.error}
            if adapter.kind == "vlm" and resp.error is None:
                store.cache_put(key, payload)
            was_cached = 0
        else:
            payload, was_cached = cached, 1
        g = grade(it.question, payload["raw"])
        row = {"run_id": run_id, "qid": it.question.qid, "task_id": it.task.task_id,
               "raw": json.dumps(payload["raw"]), "parsed": json.dumps(g.parsed), "correct": int(g.correct),
               "err": g.error, "confidence": payload["confidence"], "latency_ms": payload["latency_ms"],
               "in_tok": 0 if was_cached else payload["in_tok"], "out_tok": 0 if was_cached else payload["out_tok"],
               "note": f"error: {payload['error']}" if payload["error"] else g.note, "cached": was_cached}
        async with lock:
            buf.append(row)
            done += 1
            if len(buf) >= 20:
                store.save_responses(buf)
                buf.clear()
                store.update_run(run_id, n_done=done)
            if progress:
                progress(done, len(items), it.task.family)

    await asyncio.gather(*(one(it) for it in items))
    if buf:
        store.save_responses(buf)
    store.update_run(run_id, n_done=done)


def run_eval(dataset: str, model_id: str, base_per_family: int | None = None, families: list[str] | None = None,
             concurrency: int = 8, run_id: str | None = None, progress: Callable | None = None) -> str:
    adapter = get_adapter(model_id)
    ok, why = adapter.available()
    if not ok:
        raise RuntimeError(f"{model_id} unavailable: {why}")
    tasks, items = select_items(dataset, base_per_family, families)
    adapter.prepare(items)
    run_id = run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{model_id.replace(':', '-').replace('@', '-')}"
    cfg = {"base_per_family": base_per_family, "families": families, "concurrency": concurrency}
    store.create_run(run_id, dataset, model_id, adapter.label, time.strftime("%Y-%m-%dT%H:%M:%S"), cfg, len(items))
    try:
        asyncio.run(_run(adapter, items, run_id, concurrency, progress))
        metrics = compute_metrics(tasks, store.get_responses(run_id), adapter.price_in, adapter.price_out)
        store.update_run(run_id, status="done", metrics=metrics)
    except Exception as e:  # keep partial results visible
        store.update_run(run_id, status="failed", error=str(e))
        raise
    return run_id


def recompute(run_id: str) -> dict:
    run = store.get_run(run_id)
    adapter = get_adapter(run["model"])
    tasks, _ = select_items(run["dataset"], run["config"].get("base_per_family"), run["config"].get("families"))
    m = compute_metrics(tasks, store.get_responses(run_id), adapter.price_in, adapter.price_out)
    store.update_run(run_id, metrics=m)
    return m
