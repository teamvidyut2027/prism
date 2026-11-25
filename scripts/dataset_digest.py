"""Print a per-task digest of a dataset (image pixel hash + questions) as JSON lines, for cross-platform diffs.

    python scripts/dataset_digest.py prism-core > digest.jsonl
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prism.pipeline.factory import load_dataset  # noqa: E402

name = sys.argv[1] if len(sys.argv) > 1 else "prism-core"
_, tasks = load_dataset(name)
for t in sorted(tasks, key=lambda t: t.task_id):
    qs = hashlib.sha256("\n".join(f"{q.qid}|{q.text}|{json.dumps(q.answer)}" for q in t.questions).encode()).hexdigest()
    print(json.dumps({"id": t.task_id, "img": t.image_sha256[:16], "q": qs[:16], "family": t.family}))
