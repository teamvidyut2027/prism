"""SQLite persistence for evaluation runs, per-item responses and a response cache."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager

from .pipeline.factory import DATA_DIR

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, dataset TEXT, model TEXT, label TEXT, created TEXT, status TEXT,
  config TEXT, metrics TEXT, n_items INTEGER, n_done INTEGER DEFAULT 0, error TEXT);
CREATE TABLE IF NOT EXISTS responses (
  run_id TEXT, qid TEXT, task_id TEXT, raw TEXT, parsed TEXT, correct INTEGER, err REAL,
  confidence REAL, latency_ms REAL, in_tok INTEGER, out_tok INTEGER, note TEXT, cached INTEGER,
  PRIMARY KEY (run_id, qid));
CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, payload TEXT);
"""


def db_path():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / "prism.db"


@contextmanager
def conn():
    with _lock:
        c = sqlite3.connect(db_path(), timeout=30)
        c.row_factory = sqlite3.Row
        try:
            c.executescript(SCHEMA)
            yield c
            c.commit()
        finally:
            c.close()


def create_run(run_id, dataset, model, label, created, config, n_items):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO runs (id,dataset,model,label,created,status,config,n_items,n_done) "
                  "VALUES (?,?,?,?,?,?,?,?,0)", (run_id, dataset, model, label, created, "running",
                                                 json.dumps(config), n_items))


def update_run(run_id, **fields):
    if not fields:
        return
    for k in ("metrics", "config"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k])
    cols = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE runs SET {cols} WHERE id=?", (*fields.values(), run_id))


def save_responses(rows: list[dict]):
    with conn() as c:
        c.executemany(
            "INSERT OR REPLACE INTO responses VALUES (:run_id,:qid,:task_id,:raw,:parsed,:correct,:err,:confidence,"
            ":latency_ms,:in_tok,:out_tok,:note,:cached)", rows)


def _run_row(r) -> dict:
    d = dict(r)
    d["config"] = json.loads(d["config"] or "{}")
    d["metrics"] = json.loads(d["metrics"]) if d["metrics"] else None
    return d


def list_runs() -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT * FROM runs ORDER BY created DESC").fetchall()
    out = []
    for r in rows:
        d = _run_row(r)
        d["summary"] = (d["metrics"] or {}).get("overall")
        out.append(d)
    return out


def get_run(run_id) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return _run_row(r) if r else None


def get_responses(run_id) -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT * FROM responses WHERE run_id=?", (run_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("raw", "parsed"):
            d[k] = json.loads(d[k]) if d[k] is not None else None
        out.append(d)
    return out


def delete_run(run_id):
    with conn() as c:
        c.execute("DELETE FROM responses WHERE run_id=?", (run_id,))
        c.execute("DELETE FROM runs WHERE id=?", (run_id,))


def cache_get(key):
    with conn() as c:
        r = c.execute("SELECT payload FROM cache WHERE key=?", (key,)).fetchone()
    return json.loads(r["payload"]) if r else None


def cache_put(key, payload):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", (key, json.dumps(payload)))
