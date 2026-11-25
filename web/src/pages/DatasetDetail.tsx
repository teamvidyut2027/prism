import { useState } from "react";
import { go } from "../App";
import { api, fmtAnswer, imageUrl, type Task } from "../api";
import { StackBar } from "../components/charts";
import { Icon } from "../components/icons";
import { Badge, Card, Empty, ErrorBox, famTitle, Kpi, Modal, Seg, skillTitle, useAsync, Verified } from "../components/ui";

const REASON_COLORS: Record<string, string> = {
  accepted: "var(--good)",
  "rejected: ambiguous or degenerate scene": "#f59e0b",
  "rejected: pixel verifier disagreed with scene": "#e0393e",
  "rejected: no unambiguous question": "#a855f7",
  "rejected: near-duplicate image": "#3b82f6",
  "rejected: duplicate scene content": "#0fb5c2",
  "rejected: non-deterministic render": "#64748b",
};

export default function DatasetDetail({ name }: { name: string }) {
  const meta = useAsync(() => api.dataset(name), [name]);
  const [family, setFamily] = useState("");
  const [variant, setVariant] = useState("");
  const [difficulty, setDifficulty] = useState(0);
  const [offset, setOffset] = useState(0);
  const tasks = useAsync(() => api.datasetTasks(name, { family, variant, difficulty: difficulty || undefined, offset, limit: 24 }), [name, family, variant, difficulty, offset]);
  const [open, setOpen] = useState<Task | null>(null);

  if (meta.error) return <ErrorBox error={meta.error} />;
  if (!meta.data) return <div className="skeleton" style={{ height: 400 }} />;
  const m = meta.data, s = m.stats, h = s.headline;
  const fams = Object.keys(s.by_family);

  return (
    <>
      <div className="page-head">
        <div>
          <a className="small" href="#/datasets">← Datasets</a>
          <h1 style={{ marginTop: 6 }}>{m.name}</h1>
          <p className="lede">seed <span className="mono">{m.config.seed}</span> · {m.config.per_cell} scenes per family × difficulty · built {m.created.replace("T", " ")} in {m.build_seconds}s</p>
        </div>
        <button className="btn primary" onClick={() => go("runs")}><Icon.eval /> Evaluate on this dataset</button>
      </div>

      <div className="grid g5">
        <Kpi accent label="Questions" value={h.questions.toLocaleString()} hint={`${h.tasks} tasks · ${h.base_tasks} base scenes`} />
        <Kpi accent label="Verified gold answers" value={`${h.verified_pct}%`} tone="good" hint="scene answer == pixel answer" />
        <Kpi accent label="Question templates" value={h.templates} hint={`${h.families} families · ${Object.keys(s.skills).length} skills`} />
        <Kpi accent label="Blind-guess ceiling" value={`${h.prior_baseline_pct}%`} hint="majority answer per template" />
        <Kpi accent label="Yes/no balance" value={h.boolean_true_pct !== null ? `${h.boolean_true_pct}%` : "-"} hint="share of 'yes' gold answers" />
      </div>

      <div className="grid g2 mt">
        <Card tour="funnel" title="Rejection funnel" sub="Every attempt that did not ship, and why">
          <div className="stack">
            {fams.map((f) => {
              const fn = m.funnel[f] ?? {};
              const parts = Object.entries(fn).filter(([k]) => k === "accepted" || k.startsWith("rejected"))
                .map(([k, v]) => ({ label: k, value: v, color: REASON_COLORS[k] ?? "#94a3b8" }));
              return (
                <div key={f}>
                  <div className="row between small"><span className="strong">{famTitle[f] ?? f}</span><span className="muted">{fn.accepted ?? 0} accepted / {fn.attempts ?? 0} attempts</span></div>
                  <StackBar parts={parts} />
                </div>
              );
            })}
            <div className="legend">
              {Object.entries(REASON_COLORS).map(([k, c]) => <span key={k}><i style={{ background: c }} />{k.replace("rejected: ", "")}</span>)}
            </div>
            {Object.values(m.rejection_examples).flat().length > 0 && (
              <details><summary>Example rejection reasons</summary>
                <ul className="small mono muted">{Object.entries(m.rejection_examples).flatMap(([f, xs]) => xs.map((x, i) => <li key={f + i}>{f}: {x}</li>))}</ul>
              </details>
            )}
          </div>
        </Card>
        <Card title="Coverage" sub="Base scenes per family × difficulty, with variants and visual diversity">
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Family</th>{[1, 2, 3, 4, 5].map((d) => <th key={d} className="num">L{d}</th>)}<th className="num" title="mean pairwise 256-bit dHash distance">Diversity</th></tr></thead>
              <tbody>
                {fams.map((f) => (
                  <tr key={f}>
                    <td className="strong">{famTitle[f] ?? f}</td>
                    {[1, 2, 3, 4, 5].map((d) => <td key={d} className="num">{s.grid[f]?.[d] ?? 0}</td>)}
                    <td className="num">{s.diversity[f]?.mean_dhash_distance ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row mt">
            {Object.entries(s.variants).map(([k, v]) => <Badge key={k} tone="accent">{v} {k}</Badge>)}
          </div>
          <div className="row mt" style={{ gap: 6 }}>
            {Object.entries(s.skills).sort((a, b) => b[1] - a[1]).map(([k, v]) => <span key={k} className="chip">{skillTitle(k)} · {v}</span>)}
          </div>
        </Card>
      </div>

      <Card tour="balance" title="Answer balance per template" sub="Low majority share and high entropy mean the answer cannot be guessed from the question" className="mt">
        <div className="table-wrap" style={{ maxHeight: 360, overflow: "auto" }}>
          <table className="table">
            <thead><tr><th>Template</th><th className="num">Questions</th><th className="num">Distinct answers</th><th>Majority share</th><th className="num">Entropy</th></tr></thead>
            <tbody>
              {Object.entries(s.answer_balance).map(([t, b]) => (
                <tr key={t}>
                  <td className="mono small">{t}</td>
                  <td className="num">{s.templates[t]}</td>
                  <td className="num">{b.distinct_answers}</td>
                  <td style={{ minWidth: 180 }}>
                    <div className="accbar"><div className="track"><div className="fill" style={{ width: `${b.majority_share * 100}%`, background: b.majority_share > 0.6 ? "var(--warn)" : "var(--cyan)" }} /></div><span className="small" style={{ minWidth: 40, textAlign: "right" }}>{Math.round(b.majority_share * 100)}%</span></div>
                  </td>
                  <td className="num">{b.entropy.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Gallery" className="mt" right={
        <div className="row">
          <select className="select" value={family} onChange={(e) => { setFamily(e.target.value); setOffset(0); }}>
            <option value="">All families</option>
            {fams.map((f) => <option key={f} value={f}>{famTitle[f] ?? f}</option>)}
          </select>
          <Seg value={difficulty} onChange={(d) => { setDifficulty(d); setOffset(0); }} options={[{ value: 0, label: "All" }, ...[1, 2, 3, 4, 5].map((d) => ({ value: d, label: `L${d}` }))]} />
          <select className="select" value={variant} onChange={(e) => { setVariant(e.target.value); setOffset(0); }}>
            <option value="">All variants</option>
            {["base", "paraphrase", "perturbation", "counterfactual"].map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
      }>
        {tasks.data ? (
          tasks.data.items.length ? (
            <>
              <div className="gallery">
                {tasks.data.items.map((t) => (
                  <div key={t.task_id} className="tile" onClick={() => setOpen(t)}>
                    <div className="thumb"><img loading="lazy" src={imageUrl(name, t.image_id)} alt={t.task_id} /></div>
                    <div className="meta">
                      <div className="row between"><span className="tiny mono muted">{t.task_id}</span><span className="chip">L{t.difficulty}</span></div>
                      <div className="q1">{t.questions[0]?.text}</div>
                      <div className="row" style={{ gap: 6 }}>
                        {t.variant !== "base" && <Badge tone="accent">{t.variant}</Badge>}
                        <span className="tiny mono">→ {fmtAnswer(t.questions[0]?.answer)}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="row between mt">
                <span className="small muted">{offset + 1}–{Math.min(offset + 24, tasks.data.total)} of {tasks.data.total}</span>
                <div className="row">
                  <button className="btn sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 24))}>Previous</button>
                  <button className="btn sm" disabled={offset + 24 >= tasks.data.total} onClick={() => setOffset(offset + 24)}>Next</button>
                </div>
              </div>
            </>
          ) : <Empty title="No tasks match these filters" />
        ) : <div className="skeleton" style={{ height: 300 }} />}
      </Card>

      {open && (
        <Modal title={<span className="mono">{open.task_id}</span>} onClose={() => setOpen(null)}>
          <div className="stage">
            <div className="imgframe"><img src={imageUrl(name, open.image_id)} alt={open.task_id} /></div>
            <div className="stack">
              <div className="row"><Badge>{famTitle[open.family]}</Badge><Badge>L{open.difficulty}</Badge><Badge tone="accent">{open.variant}</Badge>
                {open.variant_info.kind && <Badge tone="warn">{open.variant_info.kind}</Badge>}</div>
              {open.questions.map((q) => (
                <div className="q" key={q.qid}>
                  <div className="row between" style={{ alignItems: "flex-start" }}><div className="qt">{q.text}</div><Verified ok={q.verified} /></div>
                  <div className="ans">
                    <span className="k">gold</span><span className="v">{fmtAnswer(q.answer)}</span>
                    <span className="k">verified</span><span className="v">{fmtAnswer(q.verified_answer)}</span>
                  </div>
                  <div className="row" style={{ marginTop: 8, gap: 6 }}><span className="chip mono">{q.template}</span>{q.skills.map((x) => <span key={x} className="chip">{skillTitle(x)}</span>)}</div>
                </div>
              ))}
              {open.variant === "counterfactual" && <div className="small">Answer flipped from <b className="mono">{fmtAnswer(open.variant_info.from)}</b> to <b className="mono">{fmtAnswer(open.variant_info.to)}</b> by a minimal scene edit.</div>}
              <details><summary>scene.json</summary><pre className="json">{JSON.stringify(open.scene, null, 2)}</pre></details>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
