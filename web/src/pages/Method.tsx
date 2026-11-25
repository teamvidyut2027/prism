import { api, type Evidence } from "../api";
import { Badge, Card, famTitle, useAsync } from "../components/ui";

export default function Method() {
  const ev = useAsync(api.evidence, []);
  const e: Evidence["summary"] | undefined = ev.data?.summary;
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Methodology</div>
          <h1>Why the answers can be trusted</h1>
          <p className="lede">Synthetic data is only useful for evaluation if the labels are right. Prism treats label correctness as something to <b>prove per item</b> and <b>audit in aggregate</b>.</p>
        </div>
      </div>
      <div className="grid g3">
        <Card title="1 · Two independent paths to the truth" className="span2">
          <div className="prose">
            <p>Each family samples a <b>scene</b> (the generative ground truth), renders it, and derives the gold answer with a pure function <code>answer(template, params, facts)</code>.</p>
            <p>Separately, a <b>pixel verifier</b> receives only the rendered image plus a public <b>manifest</b>: layout such as the plot rectangle, axis scale, legend colours and cell boxes, but never values or answers. It re-measures the facts with classical computer vision:</p>
            <ul>
              <li><b>Bar charts:</b> colour-coverage scans along each bar slot, snapped to the value grain.</li>
              <li><b>Line charts:</b> anti-aliasing-aware alpha model per series, with segment extrapolation at each tick.</li>
              <li><b>Object scenes:</b> exclusive per-colour coverage, connected components, and shape classification by solidity and enclosing-circle fill.</li>
              <li><b>Clocks:</b> radial ray profiles that separate minute and hour hands by length.</li>
              <li><b>Mazes:</b> cell sampling, marker localisation, then an independent BFS.</li>
              <li><b>Tables:</b> template OCR against glyphs rendered at several sub-pixel phases, with a margin test.</li>
            </ul>
            <p>The same <code>answer()</code> function is applied to the measured facts. A question ships only if <b>gold == verified</b>; otherwise it is dropped and counted.</p>
          </div>
        </Card>
        <Card tour="audit" title="Audit results" sub="python -m prism verify">
          {e ? (
            <div className="stack">
              <div className="row between"><span>Fresh scenes audited</span><b>{e.scenes}</b></div>
              <div className="row between"><span>Verifier agreement</span><Badge tone="good">{e.agreement_pct}%</Badge></div>
              <div className="row between"><span>Deterministic renders</span><Badge tone="good">{e.determinism_pct}%</Badge></div>
              <div className="row between"><span>Injected label corruptions</span><b>{e.corruptions}</b></div>
              <div className="row between"><span>Corruptions caught</span><Badge tone="good">{e.corruption_detection_pct}%</Badge></div>
              <div className="sep" />
              {Object.entries(e.per_family).map(([f, v]) => (
                <div key={f} className="row between small"><span>{famTitle[f] ?? f}</span><span className="muted">agree {v.agreement_pct}% · catch {v.corruption_detection_pct}%</span></div>
              ))}
            </div>
          ) : <div className="muted small">Run <code>python -m prism verify</code> to generate the audit.</div>}
        </Card>
      </div>
      <div className="grid g2 mt">
        <Card title="2 · Ambiguity is designed out">
          <div className="prose">
            <ul>
              <li>Extremes must beat the runner-up by a margin (10% of the axis at L1, down to 4% at L5).</li>
              <li>Thresholds are never within the margin of any value, and no series point sits within the separation of another.</li>
              <li>Objects never overlap; relational questions only refer to uniquely identifiable objects.</li>
              <li>Clock hands are at least 20° apart; mazes have a unique first move when that is asked.</li>
              <li>Colour names come from a palette whose closest pair is ΔE 28 apart (unit-tested).</li>
            </ul>
          </div>
        </Card>
        <Card title="3 · Meaningful variation">
          <div className="prose">
            <ul>
              <li><b>Difficulty knobs</b> per family (element count, margins, labels, numerals, grid size, font size), five levels each.</li>
              <li><b>Seeded hierarchy</b>: every task is a pure function of <code>(seed, family, level, index, attempt)</code>, so builds reproduce byte-for-byte.</li>
              <li><b>Near-duplicate filter</b> on a 256-bit perceptual hash; per-template answer balance and a blind-prior ceiling are reported.</li>
              <li><b>Counterfactual twins</b>: a minimal scene edit that flips the gold answer separates seeing from guessing.</li>
              <li><b>Perturbation twins</b> are admitted only if the verifier still recovers the same facts from the degraded pixels.</li>
            </ul>
          </div>
        </Card>
        <Card title="4 · Metrics that explain failures">
          <div className="prose">
            <ul>
              <li>Accuracy with 95% Wilson intervals by family, level, skill, template, answer type and variant.</li>
              <li><b>Consistency</b>: the same answer to a paraphrase. <b>Robustness</b>: accuracy and flip rate under perturbation.</li>
              <li><b>Grounded</b>: right on both sides of a counterfactual. <b>Stuck</b>: the same answer though the truth changed.</li>
              <li>Error magnitudes (e.g. minutes off on clocks), calibration (ECE, Brier, reliability diagram), cost and latency.</li>
            </ul>
          </div>
        </Card>
        <Card title="5 · Grading">
          <div className="prose">
            <p>Strict on meaning, lenient on format: "Seven", "7 objects" and "**7**" all parse to 7; "3:05 PM" equals 3:05; tolerance applies only to unlabeled chart readings. Each grade stores the parsed value, so every decision can be audited in the item explorer.</p>
            <p>The <b>pixel oracle</b> answers through exactly the same files, prompts and grader using only classical CV. It scores 100%, which shows the pipeline has no leakage or grading bugs.</p>
          </div>
        </Card>
      </div>
    </>
  );
}
