"""End-to-end: build a small dataset, evaluate the oracle and blind baselines, check the metrics."""
import itertools
import json

import pytest

from prism.core.palette import NAMED, delta_e
from prism.models.anthropic_vlm import AnthropicAdapter


def test_palette_colours_are_distinguishable():
    closest = min(delta_e(NAMED[a], NAMED[b]) for a, b in itertools.combinations(NAMED, 2))
    assert closest > 25


@pytest.fixture(scope="module")
def built(tmp_data):
    from prism.pipeline.factory import BuildConfig, build_dataset
    cfg = BuildConfig(name="t", per_cell=1, workers=1, seed=3)
    return build_dataset(cfg)


def test_build_summary(built, tmp_data):
    h = built["stats"]["headline"]
    assert h["verified_pct"] == 100.0
    assert h["families"] == 6
    assert h["base_tasks"] >= 25
    lines = (tmp_data / "datasets" / "t" / "tasks.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == h["tasks"]
    for line in lines:
        t = json.loads(line)
        assert (tmp_data / "datasets" / "t" / "images" / f"{t['image_id']}.png").exists()
        assert all(q["verified"] for q in t["questions"])
        assert "answer" not in json.dumps(t["manifest"]), "manifest must not leak answers"


def test_build_is_reproducible(built, tmp_data):
    from prism.pipeline.factory import BuildConfig, build_dataset
    first = (tmp_data / "datasets" / "t" / "tasks.jsonl").read_text(encoding="utf-8")
    build_dataset(BuildConfig(name="t2", per_cell=1, workers=1, seed=3))
    second = (tmp_data / "datasets" / "t2" / "tasks.jsonl").read_text(encoding="utf-8")
    sha = lambda txt: [json.loads(x)["image_sha256"] for x in txt.splitlines()]
    assert sha(first) == sha(second)


def test_oracle_scores_100_and_blind_baselines_do_not(built):
    from prism import store
    from prism.pipeline.evaluate import run_eval
    oracle = store.get_run(run_eval("t", "oracle:pixels", run_id="t-oracle"))["metrics"]
    assert oracle["overall"]["acc"] == 1.0
    assert oracle["counterfactual"]["grounded"] in (1.0, None)
    prior = store.get_run(run_eval("t", "baseline:prior", run_id="t-prior"))["metrics"]
    assert prior["overall"]["acc"] < 0.6
    if prior["counterfactual"]["pairs"]:
        assert prior["counterfactual"]["grounded"] == 0.0   # a blind model can never track a flipped answer


def test_anthropic_unavailable_without_key():
    ok, why = AnthropicAdapter().available()
    assert not ok and "ANTHROPIC_API_KEY" in why


def test_api_endpoints(built):
    from fastapi.testclient import TestClient
    from prism.server import app
    c = TestClient(app)
    assert c.get("/api/health").json()["ok"]
    assert len(c.get("/api/families").json()) == 6
    p = c.get("/api/preview", params={"family": "clocks", "difficulty": 2, "seed": 1, "index": 0}).json()
    assert p["tasks"][0]["questions"] and p["images"]
    assert any(d["name"] == "t" for d in c.get("/api/datasets").json())
    page = c.get("/api/datasets/t/tasks", params={"limit": 5}).json()
    assert page["total"] > 0 and len(page["items"]) <= 5
    img = page["items"][0]["image_id"]
    assert c.get(f"/api/datasets/t/images/{img}.png").headers["content-type"] == "image/png"
    assert c.post("/api/runs", json={"dataset": "t", "model": "anthropic:opus-5-5"}).status_code == 400
