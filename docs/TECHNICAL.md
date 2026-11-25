# Prism: technical explanation

*Innodata AI Hackathon 2026, Challenge 02 (Visual Task Factory)*

## 1. Problem framing

A visual benchmark has three failure modes that make its scores meaningless:

1. **Wrong labels.** A gold answer that does not match the image punishes correct models.
2. **Unanswerable or ambiguous items.** Occluded data, near-ties or confusable colours turn the item into a coin flip.
3. **Items solvable without the image.** Answer priors such as "the answer is usually *yes*" inflate scores and hide the lack of visual grounding.

Prism is built so each of these is either **impossible by construction** or **measured and reported**.

### Practical impact: the visual problem we chose

Teams are adopting vision-language models to **read operational visuals automatically**: KPI dashboards and charts in reports, tables in scanned statements, analog gauges and clocks on industrial equipment, floor plans and grid layouts in logistics and robotics. Before such a model is trusted with that job, two questions need hard answers:

1. *How accurate is it on exactly this kind of image, and where does accuracy collapse?*
2. *When it is wrong, is it misreading the image or not looking at it?*

Public benchmarks answer neither well: their labels are partly human-made (and partly wrong), they cannot dial difficulty up step by step, and they cannot produce an image whose answer differs by one controlled edit. Prism's image families (**charts, tables, gauges/clocks, object layouts, grid maps**) are the visual building blocks of those workloads. Its output is a pre-deployment **acceptance test**: verified tasks, a capability map by skill and difficulty, and the failure modes to guard against. For example, our run shows Anthropic Opus 5.5 reads charts perfectly, but a gauge-reading deployment should expect 1–3 minute errors on dials without numerals, and a route-planning use should not trust its "reachable" answers without a check.

## 2. Architecture

```
prism/core       Task/Question model · hierarchical seeding · CIELAB palette · alpha-blend colour model · renderer
prism/families   6 families × {sample_scene, render, facts_from_scene, question_candidates, answer, measure, mutate}
prism/validate   perturbations + recoverability · verifier audit (agreement, corruption detection)
prism/pipeline   factory (funnel + variants + dedupe) · stats · evaluation runner · metrics
prism/grading    answer parsing and grading
prism/models     Opus 5.5 vision · OpenAI-compatible VLMs · blind baselines · pixel oracle
prism/server.py  FastAPI (jobs, preview, datasets, runs, live "ask") + React SPA
```

### The family contract

Each family implements one interface (`prism/families/base.py`):

| Method | Role |
|---|---|
| `sample_scene(rng, level)` | draws a scene; raises `Rejected` if it would be ambiguous (margins, overlaps, hand separation, ...) |
| `render(scene) -> (image, manifest)` | deterministic drawing; the manifest is public layout only (plot rect, axis scale, legend colours, cell boxes) |
| `facts_from_scene(scene)` | canonical facts (values, objects, grid, time) |
| `question_candidates(scene, facts)` | every **unambiguous** (template, params) pair for the scene |
| `answer(template, params, facts)` | a **pure** function from facts to answer, shared by both truth paths |
| `measure(pixels, manifest)` | the independent verifier: facts recovered from pixels alone |
| `mutate(scene, hint)` | a minimal edit, aimed at the element a question refers to (for counterfactuals) |

### Two independent paths to the truth

```
scene ──facts_from_scene──► facts ──answer()──► gold
  └──render──► pixels ──measure()──► facts' ──answer()──► verified        ship iff gold == verified
```

`measure()` never sees scene values. Rendering bugs, clipped labels, occlusions, anti-aliasing artefacts and generator bugs all show up as a disagreement, and the item is rejected with its reason counted in the dataset funnel.

## 3. Verifiers (classical computer vision)

| Family | Technique |
|---|---|
| Bars | Per-slot colour coverage along the value axis; bar end → value; snap to the public value grain. |
| Lines | Each pixel is modelled as `paper + α·(series − paper)` (anti-aliasing-aware coverage). Two-sided segment extrapolation at each x-tick removes vertex bias. |
| Shapes | **Exclusive** coverage (each pixel goes to the palette colour whose blend model fits best, so an anti-aliased brown rim never counts as "gray"), then connected components and classification by solidity (stars) and enclosing-circle fill (circle > hexagon > square > triangle). |
| Clocks | Radial ray profiles: the minute hand is the only stroke reaching 0.56–0.68 R; the hour hand is found in 0.20–0.40 R after masking the minute angle; time recovered from angles. |
| Mazes | Exclusive coverage of wall/start/goal colours at cell centres, marker centroids → cells, independent BFS. |
| Tables | Fixed-pitch template OCR. Numbers are right-aligned monospace, so digit k sits at a known advance-width slot; templates are rendered through the same pipeline at 8 sub-pixel phases × 3 blur levels; a glyph is accepted only if the best match beats the runner-up by a margin. |

## 4. Validation evidence

`python -m prism verify --n 40` → `docs/evidence/verifier_audit.json`

* **Agreement**: share of fresh scenes whose facts the verifier recovers exactly (non-agreeing scenes are the ones the factory rejects).
* **Label-corruption detection** (mutation testing of the verifier): render an edited scene and present the original facts as labels. A verifier that rubber-stamps would score 0%. Prism catches **100%**.
* **Determinism**: every scene is rendered twice and compared byte-for-byte.
* **Perturbation recoverability** per family and kind, which decides which robustness twins are admitted.

The **pixel oracle** model (`oracle:pixels`) answers every dataset item through the same PNG files, prompts and grader and scores **100%**. That rules out leakage, mismatched images and grader bugs end to end.

## 5. Meaningful variation

* **5 difficulty levels per family** with real knobs (element counts, margins 10% → 4%, hidden value labels, numeral removal, 1-minute grain, 12×12 grids, 14px fonts, distractor second hand).
* **35 templates and 10 skills**: counting, comparison, numeric reading, spatial reasoning, text reading, arithmetic, clock reading, path reasoning, trend analysis, attribute binding.
* **Balanced answers**: boolean targets are drawn 50/50 and templates are chosen uniformly; per-template majority share and entropy are reported; the **blind prior baseline** measures the best image-free score (about 25%).
* **Dedupe**: an exact-content hash of the facts plus a 256-bit perceptual hash.
* **Controlled variants** (each changes exactly one thing):
  * *paraphrase*: same pixels, reworded question → **consistency**
  * *perturbation*: noise / blur / JPEG / downscale, admitted only if the verifier still recovers identical facts → **robustness**
  * *counterfactual*: a minimal scene edit that flips the answer while staying unambiguous → **grounding** (right on both) and **stuck rate** (same answer though the truth changed)

## 6. Evaluation and diagnosis

* Async runner with bounded concurrency and a response cache keyed by `(model, image sha256, prompt)`.
* Opus 5.5 via the Anthropic SDK: base64 image, JSON-schema structured output `{answer, confidence}`, adaptive effort, server-side refusal fallback.
* Any OpenAI-compatible VLM endpoint (Ollama, vLLM, LM Studio) for open-weight comparisons.
* Grader: strict on meaning, lenient on format; every decision stores the parsed value.
* Metrics: accuracy with Wilson 95% CIs by family, level, skill, template, answer type and variant; family × level heatmap; consistency; robustness and flip rate; grounding and stuck rate; error magnitude (e.g. minutes off); calibration (ECE, Brier, reliability bins); cost and latency.

## 7. Reproducibility

Every random choice comes from `random.Random(sha256(seed, family, level, index, attempt, ...))`. Fonts are bundled, rendering uses fixed supersampling and PNG encoding, and the near-duplicate pass runs in a fixed order after parallel generation. Rebuilding a dataset with the same config therefore produces byte-identical images and identical questions on any machine (tested in `tests/test_pipeline.py::test_build_is_reproducible`).

## 8. Assumptions

* **Ground truth is the generative scene.** The pixel verifier exists to catch cases where the rendered image does not show what the scene says (bugs, occlusion, aliasing, illegibility).
* **The manifest is public layout, not an answer.** The verifier may know where the plot area is or which colour a legend entry uses, just as a reader sees the axes and the legend. A test asserts that manifests never contain answers.
* **A task is fair only if a careful human could answer it from the image.** Hence the ambiguity margins (separations, unique extremes, hand separation, non-overlap) and the perturbation recoverability check.
* **Format is not ability.** The grader is lenient on format and strict on meaning; numeric tolerance applies only to unlabeled chart readings.
* **Models are evaluated zero-shot** with a fixed system prompt and a per-type answer instruction, one image and one question per request, with no chain-of-thought text required.

## 9. Reused components

Everything specific to the task factory (generators, renderers, verifiers, validation, metrics, grader, dashboard) was written for this project. It builds on these open-source components:

| Component | Used for |
|---|---|
| Pillow | drawing primitives, text rendering, PNG/JPEG encoding, blur/median filters |
| NumPy | pixel arrays, colour models, statistics |
| OpenCV (headless) | connected components, contours, convex hull, minimum enclosing circle (shape classifier) |
| SciPy | `map_coordinates` bilinear sampling (clock ray profiles) |
| FastAPI + Uvicorn + Pydantic | REST API and request validation |
| httpx | OpenAI-compatible VLM adapter |
| Anthropic Python SDK | Anthropic adapter |
| SQLite (stdlib) | runs, responses, response cache |
| React 18 + Vite + TypeScript | dashboard (charts are hand-written SVG, with no chart library) |
| DejaVu fonts (bundled) | deterministic text rendering |
| pytest | 67 tests |

No pre-existing benchmark, dataset or image is used; every image is generated.

## 10. Models and AI tools (declaration)

| Tool / model | Role |
|---|---|
| **Anthropic Opus 5.5** (`opus-5-5`) | Model under evaluation: full 1,747-question run, effort `low`, JSON-schema structured output `{answer, confidence}`, server-side refusal fallback enabled. |
| **Anthropic Haiku 5.5** (`haiku-5-5`) | Second model evaluated on a 443-question stratified subset from the dashboard. |
| **Anthropic's AI coding assistant** | Development assistant: wrote and refactored code, ran the tests, audits and browser checks under the team's direction. |
| OpenAI-compatible endpoint (optional) | Any local VLM (Ollama, vLLM, LM Studio) can be evaluated; none was required for the results reported. |

No LLM is used anywhere **inside the task factory**: generation, rendering, verification and grading are deterministic code, so the gold answers never depend on a model's opinion.

## 11. Repeatability

* `docker build -t prism . && docker run --rm prism python -m prism reproduce` rebuilds the benchmark from its seed, re-runs the verifier audit, the pixel oracle and the blind baselines, and compares the rebuilt dataset with the committed fingerprint (`docs/evidence/fingerprint_prism-core.json`, a SHA-256 over every image's pixels and every question and answer). It exits non-zero if any check fails.
* Dependencies are pinned to exact versions in `requirements.txt`, because byte-identical rendering requires the same Pillow/FreeType build.
* Text is shaped with Pillow's Raqm engine (HarfBuzz). On Linux this needs `libfribidi`, which the Docker image installs. Verified: a Windows build and the Linux container build produce the **same fingerprint** (`docs/evidence/logs/reproduce.log`, `logs/reproduce_docker.log`), so the dataset is byte-identical across operating systems.

## 12. Limitations and next steps

* Synthetic scenes are clean by design; photo-realistic families (rendered 3D scenes, documents with layout noise) would extend coverage.
* Table OCR verification is font-specific by construction. That is fine for a factory that controls the font, but not a general OCR.
* Counterfactual coverage is about 98% of base tasks; the rest have no single minimal edit that flips an unambiguous answer.
