import { go } from "../App";
import { api, pct, type Run } from "../api";
import { Heatmap } from "../components/charts";
import { Icon } from "../components/icons";
import { useTour } from "../components/Tour";
import { AccBar, Badge, Card, Empty, famTitle, Kpi, skillTitle, useAsync } from "../components/ui";

const STEPS = [
  { t: "Sample", d: "Seeded parametric scene per family and difficulty" },
  { t: "Disambiguate", d: "Margins: unique extremes, no overlaps, separated values" },
  { t: "Render", d: "Supersampled, bundled fonts, byte-reproducible" },
  { t: "Verify", d: "Classical CV re-reads the facts from the pixels alone" },
  { t: "Cross-check", d: "Gold answer must equal the pixel-derived answer" },
  { t: "Diversify", d: "Near-duplicate filter, balanced answers, template coverage" },
  { t: "Vary", d: "Paraphrase, perturbation, counterfactual twins" },
];

export function latestPerModel(runs: Run[]): Run[] {
  const seen = new Map<string, Run>();
  for (const r of runs) if (r.status === "done" && r.metrics && !seen.has(r.model + "|" + r.dataset)) seen.set(r.model + "|" + r.dataset, r);
  return [...seen.values()].sort((a, b) => (b.metrics!.overall.acc ?? 0) - (a.metrics!.overall.acc ?? 0));
}

export default function Overview() {
  const tour = useTour();
  const ds = useAsync(api.datasets, []);
  const runs = useAsync(api.runs, []);
  const ev = useAsync(api.evidence, []);
  const main = ds.data?.find((d) => d.name === "prism-core") ?? ds.data?.[0];
  const board = latestPerModel(runs.data ?? []).filter((r) => !main || r.dataset === main.name);
  const e = ev.data?.summary;
  const skills = [...new Set(board.flatMap((r) => Object.keys(r.metrics!.by_skill)))].sort();

  return (
    <>
      <section className="card hero">
        <div className="page-head" style={{ marginBottom: 0 }}>
          <div>
            <div className="eyebrow" style={{ fontSize: 12, fontWeight: 650, letterSpacing: ".08em", textTransform: "uppercase" }}>Innodata AI Hackathon · Visual Task Factory</div>
            <h1 style={{ marginTop: 6 }}>Visual tasks with answers you can <span className="g">prove</span>, and a map of where multimodal AI breaks.</h1>
            <p>Prism generates synthetic images and questions from seeded scenes and verifies every gold answer twice: once from the scene and once from the rendered pixels by an independent computer-vision verifier. Paraphrase, perturbation and counterfactual twins then show <i>why</i> a model fails, not just that it does.</p>
            <div className="row mt">
              <button className="btn primary" onClick={() => tour.start()}><Icon.play /> Take the guided demo</button>
              <button className="btn" onClick={() => go("factory")}><Icon.factory /> Open the factory</button>
              <button className="btn" onClick={() => go("runs")}><Icon.eval /> Evaluate a model</button>
              <button className="btn ghost" onClick={() => go("method")}>How validation works →</button>
            </div>
          </div>
        </div>
      </section>

      <div className="grid g5 mt" data-tour="kpis">
        <Kpi accent label={<><Icon.shield /> Gold answers verified</>} value={main ? `${main.stats.verified_pct}%` : "-"} hint={main ? `${main.stats.questions.toLocaleString()} questions in ${main.name}` : "build a dataset"} tone="good" />
        <Kpi accent label="Label corruptions caught" value={e ? `${e.corruption_detection_pct}%` : "-"} hint={e ? `${e.corruptions} injected errors (audit)` : "run: python -m prism verify"} tone={e ? "good" : undefined} />
        <Kpi accent label="Verifier agreement" value={e ? `${e.agreement_pct}%` : "-"} hint={e ? `${e.scenes} fresh scenes; mismatches are rejected` : ""} />
        <Kpi accent label="Deterministic renders" value={e ? `${e.determinism_pct}%` : "-"} hint="same seed, byte-identical image" />
        <Kpi accent label="Blind-guess ceiling" value={main ? `${main.stats.prior_baseline_pct}%` : "-"} hint="best image-free strategy (answer bias)" />
      </div>

      <Card title="The factory pipeline" sub="Every stage can reject a candidate; the reasons are counted and shown per dataset" className="mt">
        <div className="pipe">
          {STEPS.map((s, i) => (
            <div className="st" key={s.t}><div className="n">{String(i + 1).padStart(2, "0")}</div><div className="t">{s.t}</div><div className="d">{s.d}</div></div>
          ))}
        </div>
      </Card>

      <div className="grid g2 mt">
        <Card title="Leaderboard" sub={main ? <>on <a href={`#/dataset/${main.name}`}>{main.name}</a> · latest run per model · bars show 95% CI</> : ""} right={<button className="btn sm" onClick={() => go("runs")}>All runs</button>}>
          {board.length ? (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Model</th><th>Accuracy</th><th className="num">Robust</th><th className="num">Grounded</th></tr></thead>
                <tbody>
                  {board.map((r) => (
                    <tr key={r.id} className="click" onClick={() => go(`run/${r.id}`)}>
                      <td>
                        <div className="strong">{r.label}</div>
                        <div className="tiny muted">{r.metrics!.overall.n} items {r.model.startsWith("baseline") ? "· blind" : r.model.startsWith("oracle") ? "· integrity check" : ""}</div>
                      </td>
                      <td style={{ minWidth: 200 }}><AccBar c={r.metrics!.overall} color={r.model.startsWith("anthropic") ? undefined : "var(--border-strong)"} /></td>
                      <td className="num" title="accuracy on perturbed images">{pct(r.metrics!.robustness.perturbed_acc, 0)}</td>
                      <td className="num" title="correct on both sides of a counterfactual pair">{pct(r.metrics!.counterfactual.grounded, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <Empty title="No evaluations yet">Run the pixel oracle or a model from <a href="#/runs">Evaluations</a>.</Empty>}
        </Card>
        <Card title="Where models struggle" sub="Accuracy by skill (%), hover for counts and confidence intervals">
          {board.length ? (
            <Heatmap rows={board.map((r) => r.id)} cols={skills} rowLabel={(id) => board.find((r) => r.id === id)!.label.replace(/\(.*\)/, "")}
              colLabel={(s) => skillTitle(s).split(" ")[0]} get={(id, s) => board.find((r) => r.id === id)!.metrics!.by_skill[s]} />
          ) : <Empty title="Nothing to compare yet" />}
        </Card>
      </div>

      {main && (
        <Card title="Dataset at a glance" sub={main.name} className="mt" right={<a className="btn sm" href={`#/dataset/${main.name}`}>Open dataset</a>}>
          <div className="row" style={{ gap: 8 }}>
            <Badge>{main.stats.base_tasks} base scenes</Badge>
            <Badge>{main.stats.tasks} tasks incl. variants</Badge>
            <Badge>{main.stats.questions} questions</Badge>
            <Badge>{main.stats.templates} templates</Badge>
            <Badge>{main.stats.families} families</Badge>
            <Badge tone="accent">yes/no balance {main.stats.boolean_true_pct}% yes</Badge>
            {Object.keys(famTitle).map((f) => <span key={f} className="chip">{famTitle[f]}</span>)}
          </div>
        </Card>
      )}
    </>
  );
}
