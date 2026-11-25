import { useState } from "react";
import { api, fmtAnswer, imageUrl, pct, type Metrics } from "../api";
import { Heatmap, HBars, LineChart, Reliability } from "../components/charts";
import { Icon } from "../components/icons";
import { Badge, Card, Empty, ErrorBox, famTitle, Kpi, Seg, skillTitle, useAsync } from "../components/ui";

export default function RunDetail({ id, preset = {} }: { id: string; preset?: Record<string, string> }) {
  const run = useAsync(() => api.run(id), [id]);
  const [only, setOnly] = useState<"failures" | "all" | "correct">((preset.only as "failures" | "all" | "correct") ?? "failures");
  const [family, setFamily] = useState(preset.family ?? "");
  const [offset, setOffset] = useState(0);
  const items = useAsync(() => api.runItems(id, { only, family, offset, limit: 18 }), [id, only, family, offset]);

  if (run.error) return <ErrorBox error={run.error} />;
  if (!run.data) return <div className="skeleton" style={{ height: 400 }} />;
  const r = run.data;
  const m = r.metrics as Metrics | null;
  if (!m) return <Empty title={`Run is ${r.status}`}>{r.error ?? `${r.n_done}/${r.n_items} items answered`}</Empty>;
  const fams = Object.keys(m.by_family);

  return (
    <>
      <div className="page-head">
        <div>
          <a className="small" href="#/runs">← Evaluations</a>
          <h1 style={{ marginTop: 6 }}>{r.label}</h1>
          <p className="lede">on <a href={`#/dataset/${r.dataset}`}>{r.dataset}</a> · {m.overall.n} graded items · <span className="mono">{r.id}</span></p>
        </div>
        <div className="row">
          {r.model.startsWith("baseline") && <Badge tone="warn">blind baseline</Badge>}
          {r.model.startsWith("oracle") && <Badge tone="accent">integrity check</Badge>}
        </div>
      </div>

      <div className="grid g5" data-tour="run-kpis">
        <Kpi accent label="Accuracy" value={pct(m.overall.acc)} hint={`95% CI ${pct(m.overall.lo)}–${pct(m.overall.hi)}`} />
        <Kpi accent label="Consistency" value={pct(m.consistency.same_answer)} hint={`same answer to paraphrases (${m.consistency.pairs} pairs)`} />
        <Kpi accent label="Robustness" value={pct(m.robustness.perturbed_acc)} hint={`perturbed vs clean ${pct(m.robustness.clean_acc)} · flip ${pct(m.robustness.flip_rate)}`} />
        <Kpi accent label="Grounded" value={pct(m.counterfactual.grounded)} hint={`right on both sides of a counterfactual (${m.counterfactual.pairs})`} />
        <Kpi accent label="Stuck answers" value={pct(m.counterfactual.stuck)} hint="same answer although the truth changed" tone={(m.counterfactual.stuck ?? 0) > 0.3 ? "bad" : undefined} />
      </div>

      <div className="grid g2 mt">
        <Card title="Accuracy by family" sub="Bars show 95% Wilson confidence intervals">
          <HBars series={[r.label]} rows={fams.map((f) => ({ label: famTitle[f] ?? f, cells: [m.by_family[f]] }))} />
        </Card>
        <Card title="Difficulty curves" sub="How accuracy decays as the factory turns up the knobs">
          <LineChart xs={["L1", "L2", "L3", "L4", "L5"]} series={fams.map((f) => ({ name: famTitle[f] ?? f, values: [1, 2, 3, 4, 5].map((d) => m.family_difficulty[f]?.[d]?.acc ?? null) }))} />
        </Card>
        <Card title="Accuracy by skill">
          <HBars series={[r.label]} rows={Object.entries(m.by_skill).sort((a, b) => (a[1].acc ?? 0) - (b[1].acc ?? 0)).map(([k, c]) => ({ label: skillTitle(k), cells: [c] }))} />
        </Card>
        <Card tour="heat" title="Family × difficulty" sub="Accuracy (%)">
          <Heatmap rows={fams} cols={["1", "2", "3", "4", "5"]} rowLabel={(f) => famTitle[f] ?? f} colLabel={(c) => `L${c}`} get={(f, d) => m.family_difficulty[f]?.[d]} />
          <div className="sep" />
          <h3 style={{ marginBottom: 8 }}>By perturbation</h3>
          <HBars series={[r.label]} rows={Object.entries(m.by_perturbation).map(([k, c]) => ({ label: k, cells: [c] }))} />
        </Card>
      </div>

      <div className="grid g3 mt">
        <Card title="Hardest templates" sub="Lowest accuracy question types" className="span2">
          <div className="table-wrap" style={{ maxHeight: 340, overflow: "auto" }}>
            <table className="table">
              <thead><tr><th>Template</th><th className="num">n</th><th>Accuracy</th><th className="num">Mean error</th></tr></thead>
              <tbody>
                {Object.entries(m.by_template).sort((a, b) => (a[1].acc ?? 0) - (b[1].acc ?? 0)).map(([t, c]) => (
                  <tr key={t}>
                    <td className="mono small">{t}</td>
                    <td className="num">{c.n}</td>
                    <td style={{ minWidth: 180 }}><div className="accbar"><div className="track"><div className="fill" style={{ width: `${(c.acc ?? 0) * 100}%` }} /></div><span className="small strong" style={{ minWidth: 44, textAlign: "right" }}>{pct(c.acc, 0)}</span></div></td>
                    <td className="num small">{m.error_magnitude[t] ? `${m.error_magnitude[t].mean}${t.includes("clocks") && m.error_magnitude[t] ? " min" : ""}` : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card title="Calibration" sub={m.calibration ? `ECE ${m.calibration.ece.toFixed(3)} · Brier ${m.calibration.brier.toFixed(3)}` : "no confidences reported"}>
          {m.calibration ? <Reliability bins={m.calibration.bins} /> : <Empty title="No confidence data" />}
          <div className="sep" />
          <div className="grid g2 small">
            <div><div className="muted">Cost</div><div className="strong">${m.usage.cost_usd.toFixed(3)}</div></div>
            <div><div className="muted">Latency p50 / p95</div><div className="strong">{m.usage.latency_p50_ms ?? "-"} / {m.usage.latency_p95_ms ?? "-"} ms</div></div>
            <div><div className="muted">Tokens in / out</div><div className="strong">{m.usage.input_tokens.toLocaleString()} / {m.usage.output_tokens.toLocaleString()}</div></div>
            <div><div className="muted">Cached / errors</div><div className="strong">{m.usage.cached} / {m.usage.errors}</div></div>
          </div>
        </Card>
      </div>

      <Card tour="items" title="Item explorer" className="mt" right={
        <div className="row">
          <select className="select" value={family} onChange={(e) => { setFamily(e.target.value); setOffset(0); }}>
            <option value="">All families</option>
            {fams.map((f) => <option key={f} value={f}>{famTitle[f] ?? f}</option>)}
          </select>
          <Seg value={only} onChange={(v) => { setOnly(v); setOffset(0); }} options={[{ value: "failures", label: "Failures" }, { value: "correct", label: "Correct" }, { value: "all", label: "All" }]} />
        </div>
      }>
        {items.data ? items.data.items.length ? (
          <>
            <div className="gallery" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
              {items.data.items.map((it) => (
                <div className="tile" key={it.qid} style={{ cursor: "default" }}>
                  <div className="thumb"><img loading="lazy" src={imageUrl(r.dataset, it.image_id)} alt={it.qid} /></div>
                  <div className="meta">
                    <div className="row between"><span className="tiny mono muted">{it.task_id}</span>
                      <span className="row" style={{ gap: 4 }}>{it.variant !== "base" && <Badge tone="accent">{it.variant}</Badge>}<span className="chip">L{it.difficulty}</span></span></div>
                    <div className="small">{it.question}</div>
                    <div className="row small" style={{ gap: 8 }}>
                      <Badge tone={it.correct ? "good" : "bad"}>{it.correct ? <Icon.check /> : <Icon.x />}</Badge>
                      <span>model <b className="mono">{fmtAnswer(it.parsed ?? it.raw)}</b></span>
                      <span className="muted">gold <b className="mono">{fmtAnswer(it.gold)}</b></span>
                      {it.confidence !== null && <span className="muted tiny">conf {Math.round(it.confidence * 100)}%</span>}
                    </div>
                    {it.note && <div className="tiny muted">{it.note}</div>}
                  </div>
                </div>
              ))}
            </div>
            <div className="row between mt">
              <span className="small muted">{offset + 1}–{Math.min(offset + 18, items.data.total)} of {items.data.total}</span>
              <div className="row">
                <button className="btn sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 18))}>Previous</button>
                <button className="btn sm" disabled={offset + 18 >= items.data.total} onClick={() => setOffset(offset + 18)}>Next</button>
              </div>
            </div>
          </>
        ) : <Empty title={only === "failures" ? "No failures" : "Nothing here"}>{only === "failures" ? "Every item in this view was answered correctly." : ""}</Empty> : <div className="skeleton" style={{ height: 260 }} />}
      </Card>
    </>
  );
}
