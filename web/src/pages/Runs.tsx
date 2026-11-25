import { useEffect, useState } from "react";
import { go } from "../App";
import { api, pct } from "../api";
import { Icon } from "../components/icons";
import { AccBar, Badge, Card, Empty, ErrorBox, JobBar, useAsync, useJob } from "../components/ui";

export default function Runs() {
  const runs = useAsync(api.runs, []);
  const ds = useAsync(api.datasets, []);
  const models = useAsync(api.models, []);
  const [dataset, setDataset] = useState("");
  const [model, setModel] = useState("");
  const [basePer, setBasePer] = useState<number | "">(10);
  const [conc, setConc] = useState(8);
  const [err, setErr] = useState<string | null>(null);
  const { job, track } = useJob((j) => { runs.reload(); if (j.status === "done" && j.result?.run_id) go(`run/${j.result.run_id}`); });

  useEffect(() => { if (!dataset && ds.data?.length) setDataset(ds.data.find((d) => d.name === "prism-core")?.name ?? ds.data[0].name); }, [ds.data, dataset]);
  useEffect(() => { if (!model && models.data?.length) setModel((models.data.find((m) => m.available && m.kind === "vlm") ?? models.data.find((m) => m.available))!.id); }, [models.data, model]);
  const sel = models.data?.find((m) => m.id === model);

  const start = async () => {
    setErr(null);
    try { track(await api.startRun({ dataset, model, base_per_family: basePer === "" ? null : basePer, concurrency: conc })); }
    catch (e) { setErr((e as Error).message); }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Evaluations</div>
          <h1>Diagnose a model</h1>
          <p className="lede">Runs are stratified across families and difficulty levels, and always include each base scene's variants, so consistency, robustness and grounding can be scored on matched pairs. Responses are cached, so re-runs are free.</p>
        </div>
      </div>

      <Card title="New evaluation">
        <div className="grid g4">
          <label className="field"><span>Dataset</span>
            <select className="select" value={dataset} onChange={(e) => setDataset(e.target.value)}>
              {(ds.data ?? []).map((d) => <option key={d.name} value={d.name}>{d.name} ({d.stats.questions} q)</option>)}
            </select>
          </label>
          <label className="field"><span>Model</span>
            <select className="select" value={model} onChange={(e) => setModel(e.target.value)}>
              {(models.data ?? []).map((m) => <option key={m.id} value={m.id} disabled={!m.available}>{m.label}{m.available ? "" : ` (unavailable)`}</option>)}
            </select>
          </label>
          <label className="field"><span>Base scenes per family (blank = all)</span>
            <input className="input" type="number" min={1} value={basePer} onChange={(e) => setBasePer(e.target.value === "" ? "" : Math.max(1, Number(e.target.value)))} />
          </label>
          <label className="field"><span>Concurrency</span>
            <input className="input" type="number" min={1} max={32} value={conc} onChange={(e) => setConc(Number(e.target.value))} />
          </label>
        </div>
        <div className="row mt">
          <button className="btn primary" disabled={!dataset || !model || job?.status === "running" || !sel?.available} onClick={start}><Icon.play /> Run evaluation</button>
          {sel && <span className="small muted">{sel.kind === "oracle" ? "Integrity check: reads only pixels with classical CV; should score 100%." : sel.blind ? "Blind baseline: never looks at the image." : "Vision-language model."}</span>}
          {(models.data ?? []).filter((m) => !m.available).slice(0, 1).map((m) => <span key={m.id} className="tiny muted">· {m.label}: {m.reason}</span>)}
        </div>
        <div className="mt"><JobBar job={job} /></div>
        <ErrorBox error={err} />
      </Card>

      <Card title="Runs" className="mt">
        {runs.data?.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Model</th><th>Dataset</th><th>Accuracy (95% CI)</th><th className="num">Items</th><th>Status</th><th>Created</th><th /></tr></thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr key={r.id} className="click" onClick={() => go(`run/${r.id}`)}>
                    <td><div className="strong">{r.label}</div><div className="tiny mono muted">{r.id}</div></td>
                    <td className="small">{r.dataset}</td>
                    <td style={{ minWidth: 220 }}>{r.summary ? <AccBar c={r.summary} /> : <span className="muted small">{pct(r.n_done / Math.max(1, r.n_items))} done</span>}</td>
                    <td className="num">{r.n_items}</td>
                    <td>{r.status === "done" ? <Badge tone="good">done</Badge> : r.status === "failed" ? <Badge tone="bad" title={r.error ?? ""}>failed</Badge> : <Badge tone="warn">running</Badge>}</td>
                    <td className="small muted">{r.created.replace("T", " ")}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <button className="btn sm ghost danger" title="Delete run" onClick={async () => { if (confirm(`Delete run ${r.id}?`)) { await api.deleteRun(r.id); runs.reload(); } }}><Icon.trash /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : runs.loading ? <div className="skeleton" style={{ height: 120 }} /> : <Empty title="No runs yet">Start with the pixel oracle; it needs no API key and proves the pipeline end to end.</Empty>}
      </Card>
    </>
  );
}
