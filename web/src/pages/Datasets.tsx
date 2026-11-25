import { useState } from "react";
import { go } from "../App";
import { api } from "../api";
import { Icon } from "../components/icons";
import { Badge, Card, Empty, ErrorBox, famTitle, JobBar, useAsync, useJob } from "../components/ui";

export default function Datasets() {
  const ds = useAsync(api.datasets, []);
  const fams = useAsync(api.families, []);
  const [name, setName] = useState("my-benchmark");
  const [seed, setSeed] = useState(2026);
  const [perCell, setPerCell] = useState(4);
  const [sel, setSel] = useState<string[] | null>(null);
  const [variants, setVariants] = useState({ paraphrase: true, perturb: true, counterfactual: true });
  const [err, setErr] = useState<string | null>(null);
  const { job, track } = useJob((j) => { if (j.status === "done") ds.reload(); });
  const families = sel ?? (fams.data ?? []).map((f) => f.name);

  const build = async () => {
    setErr(null);
    try {
      track(await api.buildDataset({ name, seed, per_cell: perCell, families, ...variants }));
    } catch (e) { setErr((e as Error).message); }
  };
  const est = families.length * 5 * perCell;

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Datasets</div>
          <h1>Reproducible benchmark builds</h1>
          <p className="lede">A dataset is a pure function of its config. The same seed rebuilds byte-identical images and questions on any machine, and every build records why candidates were rejected.</p>
        </div>
      </div>

      <div className="grid g3">
        <Card title="Build a dataset" sub={`≈ ${est} base scenes · ~${Math.max(1, Math.round(est * 3.3))} tasks with variants`} className="span2">
          <div className="grid g3">
            <label className="field"><span>Name</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label className="field"><span>Seed</span><input className="input mono" type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></label>
            <label className="field"><span>Scenes per family × difficulty</span><input className="input" type="number" min={1} max={200} value={perCell} onChange={(e) => setPerCell(Math.max(1, Number(e.target.value)))} /></label>
          </div>
          <div className="field mt"><span>Families</span>
            <div className="row">
              {(fams.data ?? []).map((f) => (
                <label key={f.name} className="check">
                  <input type="checkbox" checked={families.includes(f.name)} onChange={(e) => setSel(e.target.checked ? [...families, f.name] : families.filter((x) => x !== f.name))} />
                  {f.title}
                </label>
              ))}
            </div>
          </div>
          <div className="field mt"><span>Variants</span>
            <div className="row">
              {(["paraphrase", "perturb", "counterfactual"] as const).map((k) => (
                <label key={k} className="check"><input type="checkbox" checked={variants[k]} onChange={(e) => setVariants({ ...variants, [k]: e.target.checked })} />{k === "perturb" ? "perturbation" : k}</label>
              ))}
            </div>
          </div>
          <div className="row mt">
            <button className="btn primary" disabled={job?.status === "running" || !families.length} onClick={build}><Icon.play /> Build</button>
            {job?.status === "done" && <button className="btn" onClick={() => go(`dataset/${name}`)}>Open {name} →</button>}
          </div>
          <div className="mt"><JobBar job={job} /></div>
          <ErrorBox error={err} />
        </Card>
        <Card title="CLI equivalent">
          <pre className="json" style={{ maxHeight: "none" }}>{`python -m prism build \\
  --name ${name} \\
  --seed ${seed} \\
  --per-cell ${perCell}${sel ? ` \\\n  --families ${families.join(" ")}` : ""}`}</pre>
          <div className="tiny muted mt">Output: <code>data/datasets/{name}/</code> with <code>tasks.jsonl</code>, <code>images/</code>, <code>dataset.json</code> and a dataset card.</div>
        </Card>
      </div>

      <Card title="Datasets" className="mt">
        {ds.data?.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Name</th><th>Created</th><th className="num">Base scenes</th><th className="num">Tasks</th><th className="num">Questions</th><th>Verified</th><th className="num">Blind ceiling</th><th>Families</th></tr></thead>
              <tbody>
                {ds.data.map((d) => (
                  <tr key={d.name} className="click" onClick={() => go(`dataset/${d.name}`)}>
                    <td className="strong">{d.name}<div className="tiny muted mono">seed {d.config.seed}</div></td>
                    <td className="muted small">{d.created.replace("T", " ")}</td>
                    <td className="num">{d.stats.base_tasks}</td>
                    <td className="num">{d.stats.tasks}</td>
                    <td className="num">{d.stats.questions}</td>
                    <td><Badge tone="good"><Icon.check /> {d.stats.verified_pct}%</Badge></td>
                    <td className="num">{d.stats.prior_baseline_pct}%</td>
                    <td className="small muted">{(d.config.families as string[]).map((f) => famTitle[f] ?? f).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : ds.loading ? <div className="skeleton" style={{ height: 120 }} /> : <Empty title="No datasets yet">Build one above, or run <code>python -m prism build</code>.</Empty>}
      </Card>
    </>
  );
}
