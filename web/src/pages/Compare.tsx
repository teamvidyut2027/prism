import { useEffect, useMemo, useState } from "react";
import { api, pct, type Run } from "../api";
import { HBars, LineChart } from "../components/charts";
import { Card, Empty, famTitle, skillTitle, useAsync } from "../components/ui";
import { latestPerModel } from "./Overview";

export default function Compare() {
  const runs = useAsync(api.runs, []);
  const done = useMemo(() => latestPerModel(runs.data ?? []), [runs.data]);
  const [sel, setSel] = useState<string[]>([]);
  const [full, setFull] = useState<Run[]>([]);
  useEffect(() => { if (!sel.length && done.length) setSel(done.slice(0, 4).map((r) => r.id)); }, [done, sel.length]);
  useEffect(() => { Promise.all(sel.map((id) => api.run(id))).then(setFull).catch(() => setFull([])); }, [sel]);

  const fams = [...new Set(full.flatMap((r) => Object.keys(r.metrics?.by_family ?? {})))];
  const skills = [...new Set(full.flatMap((r) => Object.keys(r.metrics?.by_skill ?? {})))].sort();
  const names = full.map((r) => r.label);

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Compare</div>
          <h1>Models side by side</h1>
          <p className="lede">The same verified items, the same grader. Blind baselines set the floor and the pixel oracle the ceiling; the space between them is what a vision model has to earn.</p>
        </div>
      </div>
      <Card title="Runs to compare" sub="latest completed run per model and dataset">
        {done.length ? (
          <div className="row">
            {done.map((r) => (
              <label key={r.id} className="check">
                <input type="checkbox" checked={sel.includes(r.id)} onChange={(e) => setSel(e.target.checked ? [...sel, r.id] : sel.filter((x) => x !== r.id))} />
                {r.label} <span className="tiny muted">({r.dataset})</span>
              </label>
            ))}
          </div>
        ) : <Empty title="No completed runs yet" />}
      </Card>
      {full.length > 0 && (
        <>
          <Card tour="compare" title="Headline" className="mt">
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Model</th><th className="num">Accuracy</th><th className="num">Base only</th><th className="num">Consistency</th><th className="num">Perturbed</th><th className="num">Flip rate</th><th className="num">Grounded</th><th className="num">Stuck</th><th className="num">ECE</th><th className="num">Cost</th></tr></thead>
                <tbody>
                  {full.map((r) => {
                    const m = r.metrics!;
                    return (
                      <tr key={r.id}>
                        <td className="strong">{r.label}</td>
                        <td className="num strong">{pct(m.overall.acc)}</td>
                        <td className="num">{pct(m.overall.base.acc)}</td>
                        <td className="num">{pct(m.consistency.same_answer)}</td>
                        <td className="num">{pct(m.robustness.perturbed_acc)}</td>
                        <td className="num">{pct(m.robustness.flip_rate)}</td>
                        <td className="num">{pct(m.counterfactual.grounded)}</td>
                        <td className="num">{pct(m.counterfactual.stuck)}</td>
                        <td className="num">{m.calibration ? m.calibration.ece.toFixed(3) : "-"}</td>
                        <td className="num">${m.usage.cost_usd.toFixed(2)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
          <div className="grid g2 mt">
            <Card title="By family"><HBars series={names} rows={fams.map((f) => ({ label: famTitle[f] ?? f, cells: full.map((r) => r.metrics!.by_family[f]) }))} /></Card>
            <Card title="Overall difficulty curve">
              <LineChart xs={["L1", "L2", "L3", "L4", "L5"]} series={full.map((r) => ({ name: r.label, values: [1, 2, 3, 4, 5].map((d) => r.metrics!.by_difficulty[d]?.acc ?? null) }))} />
            </Card>
            <Card title="By skill" className="span2"><HBars series={names} rows={skills.map((s) => ({ label: skillTitle(s), cells: full.map((r) => r.metrics!.by_skill[s]) }))} /></Card>
          </div>
        </>
      )}
    </>
  );
}
