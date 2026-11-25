"""Write docs/evidence/FAILURES.md: a model's failure cases grouped by template, with example images.

    python scripts/failure_report.py --run core-opus-5-5
"""
import argparse
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prism import store  # noqa: E402
from prism.pipeline.factory import image_path, load_dataset  # noqa: E402


def fmt(a):
    if isinstance(a, bool):
        return "yes" if a else "no"
    if isinstance(a, list):
        return ", ".join(map(str, a))
    if isinstance(a, float) and a.is_integer():
        return str(int(a))
    return str(a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="core-opus-5-5")
    ap.add_argument("--per-template", type=int, default=2)
    a = ap.parse_args()
    run = store.get_run(a.run)
    _, tasks = load_dataset(run["dataset"])
    qmap = {q.qid: (t, q) for t in tasks for q in t.questions}
    resp = store.get_responses(a.run)
    bad = [r for r in resp if not r["correct"] and r["qid"] in qmap]
    n_by_t = Counter(qmap[r["qid"]][1].template for r in resp if r["qid"] in qmap)
    bad_by_t = defaultdict(list)
    for r in sorted(bad, key=lambda r: r["qid"]):
        bad_by_t[qmap[r["qid"]][1].template].append(r)

    out = ROOT / "docs" / "evidence"
    img_dir = out / "failures"
    if img_dir.exists():
        shutil.rmtree(img_dir)
    img_dir.mkdir(parents=True)
    L = [f"# Failure cases: {run['label']} on `{run['dataset']}`", "",
         f"{len(bad)} of {len(resp)} answers were wrong ({100 * len(bad) / len(resp):.1f}%). "
         "Every failure below was graded by the same parser that gives the pixel oracle 100%, and the "
         "parsed value is shown so each grading decision can be audited.", "",
         "## Failures by template", "",
         "| Template | Wrong / asked | Accuracy | Typical error |", "|---|---:|---:|---|"]
    for t, rows in sorted(bad_by_t.items(), key=lambda kv: -len(kv[1])):
        errs = [r["err"] for r in rows if r["err"] is not None]
        unit = " min" if t.startswith("clocks") and "number" not in t else ""
        typ = (f"off by {sorted(errs)[len(errs) // 2]:g}{unit} (median of misses), max {max(errs):g}{unit}"
               if errs else "")
        if t == "mazes.reachable":
            typ = f"{sum(1 for r in rows if qmap[r['qid']][1].answer is False)}/{len(rows)} said *yes* when the goal is unreachable"
        L.append(f"| `{t}` | {len(rows)} / {n_by_t[t]} | {100 * (1 - len(rows) / n_by_t[t]):.1f}% | {typ} |")
    L += ["", "## Examples", ""]
    for t, rows in sorted(bad_by_t.items(), key=lambda kv: -len(kv[1])):
        L += [f"### `{t}`", ""]
        for r in rows[: a.per_template]:
            task, q = qmap[r["qid"]]
            shutil.copy(image_path(run["dataset"], task.image_id), img_dir / f"{task.image_id}.png")
            L += [f"**{task.task_id}** (level {task.difficulty}, {task.variant})  ", f"*{q.text}*  ",
                  f"gold **{fmt(q.answer)}** · model said `{fmt(r['raw'])}` (parsed {fmt(r['parsed'])})"
                  + (f" · confidence {r['confidence']:.2f}" if r["confidence"] is not None else ""), "",
                  f'<img src="failures/{task.image_id}.png" width="340">', ""]
    (out / "FAILURES.md").write_text("\n".join(L), encoding="utf-8")
    print(f"{len(bad)} failures, {len(list(img_dir.glob('*.png')))} example images -> docs/evidence/FAILURES.md")


if __name__ == "__main__":
    main()
