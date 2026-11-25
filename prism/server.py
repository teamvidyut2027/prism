"""FastAPI backend for the Prism dashboard."""
from __future__ import annotations

import asyncio
import base64
import threading
import time
import traceback
import uuid
from dataclasses import asdict, fields
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import store
from .core.spec import Task
from .families import REGISTRY
from .grading.grader import answer_instruction, grade
from .models import EvalItem, all_adapters, build_prompt, get_adapter
from .pipeline.evaluate import run_eval, select_items
from .pipeline.factory import BuildConfig, build_dataset, generate_cell, image_path, list_datasets, load_dataset

STATIC = Path(__file__).resolve().parent / "static"

# pick up ANTHROPIC_API_KEY etc. from the project .env when started directly with uvicorn
from .__main__ import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
app = FastAPI(title="Prism: Visual Task Factory", version="1.0.0")

# ---------------------------------------------------------------------------- jobs
JOBS: dict[str, dict] = {}


def start_job(kind: str, fn, *args, **kwargs) -> dict:
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "kind": kind, "status": "running", "done": 0, "total": 0, "detail": "", "result": None,
           "error": None, "started": time.time()}
    JOBS[jid] = job

    def progress(done, total, detail=""):
        job.update(done=done, total=total, detail=detail)

    def target():
        try:
            job["result"] = fn(*args, progress=progress, **kwargs)
            job["status"] = "done"
        except Exception as e:  # surfaced to the UI
            job.update(status="failed", error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-2000:])

    threading.Thread(target=target, daemon=True).start()
    return job


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    if jid not in JOBS:
        raise HTTPException(404, "no such job")
    j = dict(JOBS[jid])
    j.pop("trace", None)
    j["elapsed"] = round(time.time() - j["started"], 1)
    return j


# ---------------------------------------------------------------------------- catalogue
@app.get("/api/health")
def health():
    return {"ok": True, "families": list(REGISTRY), "datasets": len(list_datasets())}


@app.get("/api/families")
def families():
    return [f.describe() for f in REGISTRY.values()]


def _png_b64(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


def _public_task(t: dict) -> dict:
    t = dict(t)
    for q in t["questions"]:
        q["instruction"] = answer_instruction(_q(q))
    return t


def _q(qd):
    from .core.spec import Question
    return Question.from_dict(qd) if isinstance(qd, dict) else qd


@app.get("/api/preview")
def preview(family: str, difficulty: int = 3, seed: int = 7, index: int = 0):
    if family not in REGISTRY:
        raise HTTPException(404, "unknown family")
    t0 = time.perf_counter()
    cfg = asdict(BuildConfig())
    res = generate_cell(family, seed, max(1, min(5, difficulty)), index, cfg)
    ms = (time.perf_counter() - t0) * 1000
    tasks = [_public_task(t) for t in res["tasks"]]
    return {"family": family, "difficulty": difficulty, "seed": seed, "index": index, "elapsed_ms": round(ms),
            "events": res["events"], "examples": res["examples"], "tasks": tasks,
            "images": {k: _png_b64(v) for k, v in res["images"].items()}}


# ---------------------------------------------------------------------------- datasets
class BuildRequest(BaseModel):
    name: str = Field("prism-core", pattern=r"^[A-Za-z0-9_.-]{1,60}$")
    seed: int = 2026
    families: list[str] | None = None
    difficulties: list[int] = [1, 2, 3, 4, 5]
    per_cell: int = Field(6, ge=1, le=200)
    questions_per_task: int = Field(3, ge=1, le=6)
    paraphrase: bool = True
    perturb: bool = True
    counterfactual: bool = True


@app.get("/api/datasets")
def datasets():
    return list_datasets()


@app.post("/api/datasets")
def create_dataset(req: BuildRequest):
    cfg = BuildConfig(**{**req.model_dump(), "families": req.families or list(REGISTRY)})
    return start_job("build", build_dataset, cfg)


@app.get("/api/datasets/{name}")
def dataset(name: str):
    try:
        meta, _ = load_dataset(name)
    except FileNotFoundError:
        raise HTTPException(404, "no such dataset")
    return meta


@app.get("/api/datasets/{name}/tasks")
def dataset_tasks(name: str, family: str | None = None, difficulty: int | None = None, variant: str | None = None,
                  offset: int = 0, limit: int = Query(48, le=500)):
    _, tasks = load_dataset(name)
    sel = [t for t in tasks if (not family or t.family == family) and (not difficulty or t.difficulty == difficulty)
           and (not variant or t.variant == variant)]
    return {"total": len(sel), "items": [_public_task(t.to_dict()) for t in sel[offset:offset + limit]]}


@app.get("/api/datasets/{name}/images/{image_id}.png")
def dataset_image(name: str, image_id: str):
    p = image_path(name, image_id)
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------------------- models & runs
@app.get("/api/models")
def models():
    return [a.describe() for a in all_adapters()]


class RunRequest(BaseModel):
    dataset: str
    model: str
    base_per_family: int | None = Field(None, ge=1, le=10000)
    families: list[str] | None = None
    concurrency: int = Field(8, ge=1, le=32)


def _run_job(req: RunRequest, progress):
    rid = run_eval(req.dataset, req.model, req.base_per_family, req.families, req.concurrency, progress=progress)
    return {"run_id": rid}


@app.post("/api/runs")
def create_run(req: RunRequest):
    try:
        a = get_adapter(req.model)
    except KeyError as e:
        raise HTTPException(400, str(e))
    ok, why = a.available()
    if not ok:
        raise HTTPException(400, why)
    return start_job("eval", _run_job, req)


@app.get("/api/runs")
def runs():
    return store.list_runs()


@app.get("/api/runs/{run_id}")
def run(run_id: str):
    r = store.get_run(run_id)
    if not r:
        raise HTTPException(404)
    return r


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    store.delete_run(run_id)
    return {"deleted": run_id}


@app.get("/api/runs/{run_id}/items")
def run_items(run_id: str, only: str = "all", family: str | None = None, variant: str | None = None,
              offset: int = 0, limit: int = Query(60, le=1000)):
    r = store.get_run(run_id)
    if not r:
        raise HTTPException(404)
    _, tasks = load_dataset(r["dataset"])
    qmap = {q.qid: (t, q) for t in tasks for q in t.questions}
    rows = []
    for x in sorted(store.get_responses(run_id), key=lambda x: x["qid"]):
        if x["qid"] not in qmap:
            continue
        t, q = qmap[x["qid"]]
        if (only == "failures" and x["correct"]) or (only == "correct" and not x["correct"]):
            continue
        if (family and t.family != family) or (variant and t.variant != variant):
            continue
        rows.append({**x, "family": t.family, "difficulty": t.difficulty, "variant": t.variant,
                     "image_id": t.image_id, "question": q.text, "template": q.template, "gold": q.answer,
                     "answer_type": q.answer_type.value, "skills": q.skills, "tolerance": q.tolerance,
                     "variant_info": t.variant_info})
    return {"total": len(rows), "items": rows[offset:offset + limit]}


class AskRequest(BaseModel):
    model: str
    family: str
    difficulty: int = 3
    seed: int = 7
    index: int = 0
    task_id: str
    qid: str


@app.post("/api/ask")
async def ask(req: AskRequest):
    """Ask one model one question from a preview cell, live."""
    adapter = get_adapter(req.model)
    ok, why = adapter.available()
    if not ok:
        raise HTTPException(400, why)
    if adapter.blind:
        raise HTTPException(400, "blind baselines need a whole dataset")
    res = await asyncio.to_thread(generate_cell, req.family, req.seed, req.difficulty, req.index, asdict(BuildConfig()))
    task = next((Task.from_dict(t) for t in res["tasks"] if t["task_id"] == req.task_id), None)
    if task is None:
        raise HTTPException(404, "task not found")
    q = next((q for q in task.questions if q.qid == req.qid), None)
    if q is None:
        raise HTTPException(404, "question not found")
    item = EvalItem(task=task, question=q, image_png=res["images"][task.image_id], prompt=build_prompt(q))
    resp = await adapter.answer(item)
    g = grade(q, resp.raw)
    return {"raw": resp.raw, "parsed": g.parsed, "correct": g.correct, "error": resp.error, "gold": q.answer,
            "confidence": resp.confidence, "latency_ms": round(resp.latency_ms), "prompt": item.prompt}


@app.get("/api/evidence")
def evidence():
    """Verifier audit produced by ``python -m prism verify`` (None if not generated yet)."""
    p = Path(__file__).resolve().parent.parent / "docs" / "evidence" / "verifier_audit.json"
    if not p.exists():
        return None
    import json
    data = json.loads(p.read_text(encoding="utf-8"))
    return {"summary": data["summary"]}


# ---------------------------------------------------------------------------- SPA
if STATIC.exists():
    if (STATIC / "assets").exists():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = STATIC / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(STATIC / "index.html")
