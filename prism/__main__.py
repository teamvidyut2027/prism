"""Command line interface.

    python -m prism build   --name prism-core --per-cell 8
    python -m prism eval    --dataset prism-core --model oracle:pixels
    python -m prism verify  --n 200              # validation evidence: verifier agreement on fresh scenes
    python -m prism report  --run <run-id>
    python -m prism serve   [--port 8000]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """KEY=VALUE lines; real environment variables win. PRISM_NO_DOTENV=1 disables it (tests)."""
    if os.environ.get("PRISM_NO_DOTENV") == "1" or not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def bar(done, total, detail=""):
    w = 30
    f = int(w * done / max(1, total))
    sys.stderr.write(f"\r  [{'#' * f}{'.' * (w - f)}] {done}/{total} {detail:<20}")
    if done == total:
        sys.stderr.write("\n")


def cmd_build(a):
    from .pipeline.factory import BuildConfig, build_dataset
    cfg = BuildConfig(name=a.name, seed=a.seed, per_cell=a.per_cell, questions_per_task=a.questions,
                      families=a.families or BuildConfig().families, workers=a.workers)
    s = build_dataset(cfg, progress=bar)
    print(json.dumps(s["stats"]["headline"], indent=2))
    print(f"built in {s['build_seconds']}s -> data/datasets/{a.name}")


def cmd_eval(a):
    from . import store
    from .pipeline.evaluate import run_eval
    rid = run_eval(a.dataset, a.model, a.base_per_family, a.families, a.concurrency, run_id=a.run_id, progress=bar)
    print_report(store.get_run(rid))


def print_report(run):
    m = run["metrics"]
    o = m["overall"]
    print(f"\n{run['label']} on {run['dataset']}: {o['acc']:.1%} ({o['correct']}/{o['n']}), "
          f"95% CI {o['lo']:.1%}-{o['hi']:.1%}")
    for title, key in (("family", "by_family"), ("difficulty", "by_difficulty"), ("skill", "by_skill"),
                       ("variant", "by_variant")):
        print(f"  by {title}:")
        for k, v in m[key].items():
            print(f"    {str(k):<22} {v['acc']:>6.1%}  (n={v['n']})")
    for k in ("consistency", "robustness", "counterfactual", "calibration", "usage"):
        if k in m:
            v = {kk: vv for kk, vv in m[k].items() if kk != "bins"}
            print(f"  {k}: {v}")


def cmd_report(a):
    from . import store
    run = store.get_run(a.run) if a.run else (store.list_runs() or [None])[0]
    if not run:
        sys.exit("no runs yet")
    print_report(store.get_run(run["id"]))


def cmd_verify(a):
    from .validate.audit import audit
    rep = audit(n_per_cell=a.n, seed=a.seed, progress=bar)
    print(json.dumps(rep["summary"], indent=2))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"written {out}")


def cmd_export(a):
    """Write evidence files (run metrics, dataset summary) and a markdown results table into docs/."""
    import shutil
    from . import store
    from .pipeline.factory import DATA_DIR
    out = Path(a.out)
    (out / "runs").mkdir(parents=True, exist_ok=True)
    runs = [r for r in store.list_runs() if r["status"] == "done" and (not a.dataset or r["dataset"] == a.dataset)]
    latest = {}
    for r in runs:                      # newest first: keep the latest run per model and dataset
        latest.setdefault((r["model"], r["dataset"]), r)
    rows = []
    for r in latest.values():
        full = store.get_run(r["id"])
        (out / "runs" / f"{r['id']}.json").write_text(json.dumps(full, indent=2), encoding="utf-8")
        m = full["metrics"]
        f = lambda x: "-" if x is None else f"{100 * x:.1f}%"
        rows.append((m["overall"]["acc"], f"| {full['label']} | {full['dataset']} | {m['overall']['n']} | "
                     f"**{f(m['overall']['acc'])}** ({f(m['overall']['lo'])}-{f(m['overall']['hi'])}) | "
                     f"{f(m['consistency']['same_answer'])} | {f(m['robustness']['perturbed_acc'])} | "
                     f"{f(m['counterfactual']['grounded'])} | {f(m['counterfactual']['stuck'])} |"))
    table = ["| Model | Dataset | Items | Accuracy (95% CI) | Consistency | Perturbed acc. | Grounded | Stuck |",
             "|---|---|---:|---|---:|---:|---:|---:|"] + [x for _, x in sorted(rows, key=lambda t: -t[0])]
    (out / "RESULTS.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    from .pipeline.factory import fingerprint, load_dataset
    for d in {r["dataset"] for r in latest.values()}:
        src = DATA_DIR / "datasets" / d / "dataset.json"
        if src.exists():
            shutil.copy(src, out / f"dataset_{d}.json")
            fp = fingerprint(load_dataset(d)[1])
            (out / f"fingerprint_{d}.json").write_text(json.dumps(fp, indent=2), encoding="utf-8")
    print("\n".join(table))
    print(f"\nwritten to {out}")


def cmd_reproduce(a):
    """One command for judges: rebuild the benchmark from its seed, re-run every validation layer,
    and check the result against the committed fingerprint. Exits non-zero if any check fails."""
    import time
    from . import store
    from .pipeline.evaluate import run_eval
    from .pipeline.factory import BuildConfig, build_dataset, fingerprint, load_dataset
    from .validate.audit import audit
    t0 = time.time()
    root = Path(__file__).resolve().parent.parent
    print(f"[1/4] building {a.name} from seed {a.seed} ...")
    s = build_dataset(BuildConfig(name=a.name, seed=a.seed, per_cell=a.per_cell), progress=bar)
    h = s["stats"]["headline"]
    fp = fingerprint(load_dataset(a.name)[1])
    print(f"[2/4] auditing the pixel verifier on {a.n} fresh scenes per family x level ...")
    ev = audit(n_per_cell=a.n, seed=99, progress=bar)["summary"]
    print("[3/4] evaluating the pixel oracle and blind baselines ...")
    res = {}
    for m in ("oracle:pixels", "baseline:prior", "baseline:random"):
        rid = run_eval(a.name, m, run_id=f"reproduce-{a.name}-{m.replace(':', '-')}", progress=bar)
        res[m] = store.get_run(rid)["metrics"]
    print("[4/4] checking results")
    ref = root / "docs" / "evidence" / f"fingerprint_{a.name}.json"
    want = json.loads(ref.read_text(encoding="utf-8")) if ref.exists() else None
    checks = [
        ("every shipped gold answer verified from pixels", h["verified_pct"] == 100.0, f"{h['verified_pct']}% of {h['questions']}"),
        ("pixel oracle scores 100% end to end", res["oracle:pixels"]["overall"]["acc"] == 1.0,
         f"{res['oracle:pixels']['overall']['correct']}/{res['oracle:pixels']['overall']['n']}"),
        ("verifier catches every injected label corruption", ev["corruption_detection_pct"] == 100.0,
         f"{ev['corruption_detection_pct']}% of {ev['corruptions']}"),
        ("renders are deterministic", ev["determinism_pct"] == 100.0, f"{ev['determinism_pct']}%"),
        ("verifier agreement on fresh scenes >= 98%", ev["agreement_pct"] >= 98.0, f"{ev['agreement_pct']}%"),
        ("blind prior baseline stays below 40%", res["baseline:prior"]["overall"]["acc"] < 0.40,
         f"{100 * res['baseline:prior']['overall']['acc']:.1f}%"),
    ]
    if want and a.seed == 2026 and a.per_cell == 8:
        checks.append(("byte-identical to the committed benchmark", fp["sha256"] == want["sha256"],
                       f"{fp['sha256'][:16]}... vs {want['sha256'][:16]}..."))
    print()
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<52} {detail}")
    from .core.render import text_engine
    print(f"\n  dataset: {h['questions']} questions, {h['tasks']} tasks, fingerprint {fp['sha256'][:16]}...  "
          f"(text engine: {text_engine()}, {time.time() - t0:.0f}s)")
    if want and fp["sha256"] != want["sha256"] and text_engine() != "raqm":
        print("  hint: Pillow's Raqm text shaper is unavailable here, so label kerning differs from the committed build.\n"
              "        Install libfribidi (apt install libfribidi0) or use the Docker image.")
    if not all(ok for _, ok, _ in checks):
        sys.exit(1)


def cmd_serve(a):
    import uvicorn
    uvicorn.run("prism.server:app", host=a.host, port=a.port, log_level="info")


def main(argv=None):
    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")
    p = argparse.ArgumentParser(prog="prism", description="Prism: Visual Task Factory")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="generate a verified dataset")
    b.add_argument("--name", default="prism-core")
    b.add_argument("--seed", type=int, default=2026)
    b.add_argument("--per-cell", type=int, default=8, help="base scenes per family x difficulty")
    b.add_argument("--questions", type=int, default=3)
    b.add_argument("--families", nargs="*")
    b.add_argument("--workers", type=int, default=0)
    b.set_defaults(fn=cmd_build)
    e = sub.add_parser("eval", help="evaluate a model on a dataset")
    e.add_argument("--dataset", default="prism-core")
    e.add_argument("--model", default="oracle:pixels")
    e.add_argument("--base-per-family", type=int)
    e.add_argument("--families", nargs="*")
    e.add_argument("--concurrency", type=int, default=8)
    e.add_argument("--run-id")
    e.set_defaults(fn=cmd_eval)
    r = sub.add_parser("report", help="print a run report")
    r.add_argument("--run")
    r.set_defaults(fn=cmd_report)
    v = sub.add_parser("verify", help="audit the verifier on fresh scenes (validation evidence)")
    v.add_argument("--n", type=int, default=40, help="scenes per family x difficulty")
    v.add_argument("--seed", type=int, default=99)
    v.add_argument("--out", default="docs/evidence/verifier_audit.json")
    v.set_defaults(fn=cmd_verify)
    x = sub.add_parser("export", help="write run metrics + results table to docs/evidence")
    x.add_argument("--dataset")
    x.add_argument("--out", default="docs/evidence")
    x.set_defaults(fn=cmd_export)
    rp = sub.add_parser("reproduce", help="judges: rebuild + validate + compare to the committed fingerprint")
    rp.add_argument("--name", default="prism-core")
    rp.add_argument("--seed", type=int, default=2026)
    rp.add_argument("--per-cell", type=int, default=8)
    rp.add_argument("--n", type=int, default=20, help="audit scenes per family x level")
    rp.set_defaults(fn=cmd_reproduce)
    s = sub.add_parser("serve", help="run the dashboard")
    s.add_argument("--host", default=os.environ.get("PRISM_HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("PRISM_PORT", "8000")))
    s.set_defaults(fn=cmd_serve)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
