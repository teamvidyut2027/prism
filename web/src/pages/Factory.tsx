import { useEffect, useMemo, useState } from "react";
import { api, fmtAnswer, type Family, type ModelInfo, type Preview, type Question, type Task } from "../api";
import { familyIcon, Icon } from "../components/icons";
import { Badge, Card, ErrorBox, Seg, skillTitle, useAsync, Verified } from "../components/ui";

const DIFF_LABEL = ["", "Warm-up", "Easy", "Medium", "Hard", "Expert"];

export default function Factory({ preset = {} }: { preset?: Record<string, string> }) {
  const fams = useAsync(api.families, []);
  const models = useAsync(api.models, []);
  const [family, setFamily] = useState(preset.family ?? "bars");
  const [difficulty, setDifficulty] = useState(Number(preset.difficulty) || 3);
  const [seed, setSeed] = useState(preset.seed !== undefined ? Number(preset.seed) : 7);
  const [index, setIndex] = useState(Number(preset.index) || 0);
  const [data, setData] = useState<Preview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.preview(family, difficulty, seed, index).then(
      (d) => { if (alive) { setData(d); setErr(null); setLoading(false); } },
      (e: Error) => { if (alive) { setErr(e.message); setLoading(false); } },
    );
    return () => { alive = false; };
  }, [family, difficulty, seed, index]);

  const fam = fams.data?.find((f) => f.name === family);
  const base = data?.tasks.find((t) => t.variant === "base");
  const vlms = (models.data ?? []).filter((m) => m.kind !== "baseline");

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">Task Factory</div>
          <h1>Generate, render, verify, live</h1>
          <p className="lede">Every task is drawn from a seeded scene, rendered deterministically, then <b>re-measured from pixels alone</b> by an independent classical-CV verifier. A question ships only when both answers agree.</p>
        </div>
      </div>

      <div className="fam-tabs">
        {(fams.data ?? []).map((f: Family) => (
          <button key={f.name} className={`fam-tab ${f.name === family ? "on" : ""}`} onClick={() => { setFamily(f.name); setIndex(0); }}>
            <span className="fam-ico">{familyIcon(f.name)}</span>
            <span>
              <div className="t">{f.title}</div>
              <div className="s">{Object.keys(f.templates).length} templates</div>
            </span>
          </button>
        ))}
      </div>

      <div className="card card-pad mt row between">
        <div className="row" style={{ gap: 18 }}>
          <div className="field">
            <span>Difficulty</span>
            <Seg value={difficulty} onChange={setDifficulty} options={[1, 2, 3, 4, 5].map((d) => ({ value: d, label: d }))} />
          </div>
          <div className="field">
            <span>Seed</span>
            <input className="input mono" style={{ width: 110 }} type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value) || 0)} />
          </div>
          <div className="field">
            <span>Scene #</span>
            <div className="row" style={{ gap: 6 }}>
              <button className="btn sm" onClick={() => setIndex(Math.max(0, index - 1))} aria-label="Previous scene"><Icon.back /></button>
              <span className="mono strong" style={{ minWidth: 28, textAlign: "center" }}>{index}</span>
              <button className="btn sm" onClick={() => setIndex(index + 1)} aria-label="Next scene" style={{ transform: "scaleX(-1)" }}><Icon.back /></button>
            </div>
          </div>
          <button className="btn" onClick={() => { setSeed(Math.floor(Math.random() * 100000)); setIndex(0); }}><Icon.shuffle /> Surprise me</button>
        </div>
        <div className="row small muted">
          {loading ? <span className="spinner" /> : data && <span>generated + verified in <b className="mono">{data.elapsed_ms} ms</b></span>}
          <Badge tone="accent">{DIFF_LABEL[difficulty]}</Badge>
        </div>
      </div>

      <ErrorBox error={err} />

      {fam && (
        <div className="small muted mt" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <b style={{ color: "var(--text-2)" }}>What difficulty changes:</b>
          {Object.entries(fam.knobs).map(([k, v]) => <span key={k} className="chip">{k}: {v}</span>)}
        </div>
      )}

      {data && base && (
        <>
          <div className="stage mt" data-tour="stage">
            <Card title={fam?.title ?? family} sub={<span className="mono">{base.task_id} · {base.width}×{base.height} · sha256 {base.image_sha256.slice(0, 12)}…</span>}>
              <div className="imgframe" style={{ opacity: loading ? 0.6 : 1, transition: "opacity .15s" }}>
                <img src={data.images[base.image_id]} alt={`Generated ${family} task`} />
              </div>
            </Card>
            <div className="stack">
              <Card title="Questions" sub="Gold answer from the scene · verified answer from the pixels">
                {base.questions.map((q, qi) => (
                  <QuestionCard key={q.qid} index={qi} q={q} task={base} models={vlms} ctx={{ family, difficulty, seed, index }} />
                ))}
              </Card>
              <Trace data={data} base={base} />
            </div>
          </div>
          <Variants data={data} base={base} />
          <Card title="Scene & manifest" sub="The scene is the ground truth. The manifest is the public layout the verifier may use; it holds no answers." className="mt">
            <div className="grid g2">
              <details open><summary>scene.json</summary><pre className="json">{JSON.stringify(base.scene, null, 2)}</pre></details>
              <details><summary>manifest.json</summary><pre className="json">{JSON.stringify(base.manifest, null, 2)}</pre></details>
            </div>
          </Card>
        </>
      )}
      {!data && !err && <div className="skeleton mt" style={{ height: 420 }} />}
    </>
  );
}

function QuestionCard({ q, task, models, ctx, index }: { q: Question; task: Task; models: ModelInfo[]; ctx: { family: string; difficulty: number; seed: number; index: number }; index: number }) {
  const [model, setModel] = useState<string>("");
  const [res, setRes] = useState<Awaited<ReturnType<typeof api.ask>> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const avail = useMemo(() => models.filter((m) => m.available), [models]);
  useEffect(() => { setRes(null); setErr(null); }, [q.qid, task.image_sha256]);
  useEffect(() => { if (!model && avail.length) setModel(avail[0].id); }, [avail, model]);

  const ask = async () => {
    setBusy(true); setErr(null);
    try {
      setRes(await api.ask({ model, task_id: task.task_id, qid: q.qid, ...ctx }));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="q" data-tour={index === 0 ? "q0" : undefined}>
      <div className="row between" style={{ alignItems: "flex-start" }}>
        <div className="qt">{q.text}</div>
        <Verified ok={q.verified} />
      </div>
      <div className="tiny muted" style={{ marginTop: 4 }}>{q.instruction}</div>
      <div className="ans">
        <span className="k">gold (scene)</span><span className="v">{fmtAnswer(q.answer)}{q.tolerance ? <span className="muted"> ± {q.tolerance}</span> : null}</span>
        <span className="k">verified (pixels)</span><span className="v">{fmtAnswer(q.verified_answer)}</span>
      </div>
      <div className="row" style={{ marginTop: 10, gap: 6 }}>
        <span className="chip mono">{q.template}</span>
        <span className="chip">{q.answer_type}</span>
        {q.skills.map((s) => <span key={s} className="chip">{skillTitle(s)}</span>)}
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <select className="select" value={model} onChange={(e) => setModel(e.target.value)} style={{ flex: 1, minWidth: 160 }}>
          {models.map((m) => <option key={m.id} value={m.id} disabled={!m.available}>{m.label}{m.available ? "" : ` (${m.reason})`}</option>)}
        </select>
        <button className="btn sm primary" data-tour={index === 0 ? "ask0" : undefined} disabled={!model || busy || !avail.length} onClick={ask}>
          {busy ? <span className="spinner" /> : <Icon.play />} Ask
        </button>
      </div>
      {err && <div className="err mt" style={{ marginTop: 8 }}>{err}</div>}
      {res && (
        <div className="row" style={{ marginTop: 10, gap: 8 }}>
          <Badge tone={res.correct ? "good" : "bad"}>{res.correct ? <Icon.check /> : <Icon.x />} {res.correct ? "correct" : "wrong"}</Badge>
          <span className="mono small">answered <b>{fmtAnswer(res.raw)}</b></span>
          {res.confidence !== null && <span className="small muted">conf {Math.round(res.confidence * 100)}%</span>}
          <span className="small muted">{res.latency_ms} ms</span>
          {res.error && <span className="small" style={{ color: "var(--bad)" }}>{res.error}</span>}
        </div>
      )}
    </div>
  );
}

function Trace({ data, base }: { data: Preview; base: Task }) {
  const ev = data.events;
  const rejections = Object.entries(ev).filter(([k]) => k.startsWith("rejected") || k.startsWith("questions dropped"));
  const v = base.validation as Record<string, any>;
  return (
    <Card tour="trace" title="Validation trace" sub={`${ev.attempts ?? 1} attempt${(ev.attempts ?? 1) > 1 ? "s" : ""} for this cell`}>
      <div className="trace">
        {rejections.map(([k, n]) => (
          <div className="step" key={k}>
            <span className="dot no">{n}</span>
            <div className="small">{k.replace(/^rejected: /, "Rejected: ")}</div>
            <span />
          </div>
        ))}
        {data.examples.map((e, i) => (
          <div className="step" key={"ex" + i}><span className="dot info">i</span><div className="small mono muted">{e}</div><span /></div>
        ))}
        <Step ok label="Ambiguity margins satisfied" detail="extremes separated, labels unique, no overlaps" />
        <Step ok label="Deterministic render" detail="re-rendered, byte-identical pixels" />
        <Step ok={v?.verifier === "pass"} label="Pixel verifier recovered the scene" detail="classical CV, no access to scene values" />
        <Step ok label={`${v?.questions_verified ?? base.questions.length} question(s) cross-checked`} detail="gold answer == answer re-derived from pixels" />
      </div>
    </Card>
  );
}

function Step({ ok, label, detail }: { ok: boolean; label: string; detail: string }) {
  return (
    <div className="step">
      <span className={`dot ${ok ? "ok" : "no"}`}>{ok ? "✓" : "✗"}</span>
      <div><div className="small strong">{label}</div><div className="tiny muted">{detail}</div></div>
      <span />
    </div>
  );
}

function Variants({ data, base }: { data: Preview; base: Task }) {
  const para = data.tasks.find((t) => t.variant === "paraphrase");
  const pert = data.tasks.find((t) => t.variant === "perturbation");
  const cf = data.tasks.find((t) => t.variant === "counterfactual");
  const orig = (qid: string | undefined) => base.questions.find((q) => q.qid === qid);
  return (
    <div className="mt-lg" data-tour="variants">
      <div className="row between" style={{ marginBottom: 12 }}>
        <div>
          <h2>Controlled variants</h2>
          <div className="small muted">Each one changes exactly one thing, so a model's failure can be attributed to a single cause.</div>
        </div>
      </div>
      <div className="variants">
        <Card title="Paraphrase" sub="Same pixels, reworded question. Tests consistency.">
          {para ? (
            <div className="stack">
              <div className="small"><span className="muted">original</span><div className="strong">{orig(Object.values(para.variant_info.pairs ?? {})[0] as string)?.text}</div></div>
              <div className="small"><span className="muted">paraphrase</span><div className="strong">{para.questions[0].text}</div></div>
              <div className="row"><span className="muted small">same gold answer</span><span className="mono strong">{fmtAnswer(para.questions[0].answer)}</span></div>
            </div>
          ) : <div className="muted small">No multi-phrasing template in this cell.</div>}
        </Card>
        <Card title="Perturbation" sub="Same scene, degraded pixels. Tests robustness.">
          {pert ? (
            <div className="stack variant">
              <img src={data.images[pert.image_id]} alt="perturbed" />
              <div className="row"><Badge tone="warn">{pert.variant_info.kind} · strength {pert.variant_info.strength}</Badge><Verified ok label="answer recoverable" /></div>
            </div>
          ) : <div className="muted small">Dropped: the verifier could not recover the facts after degradation, so this cell has no perturbation twin.</div>}
        </Card>
        <Card title="Counterfactual" sub="Minimal scene edit that flips the answer. Tests grounding.">
          {cf ? (
            <div className="stack variant">
              <img src={data.images[cf.image_id]} alt="counterfactual" />
              <div className="small strong">{cf.questions[0].text}</div>
              <div className="flip"><span className="from">{fmtAnswer(cf.variant_info.from)}</span>→<span className="to">{fmtAnswer(cf.variant_info.to)}</span></div>
            </div>
          ) : <div className="muted small">No single minimal edit flipped an unambiguous answer for this cell.</div>}
        </Card>
      </div>
    </div>
  );
}
