// Guided demo: a scripted walkthrough that drives the real dashboard.
// Each step navigates to a deep link, waits for its target to render, spotlights it and narrates the claim.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, pct, type Evidence, type Run } from "../api";
import { Icon } from "./icons";

interface TourData {
  evidence: Evidence["summary"] | null;
  vlm: Run | null;
  oracle: Run | null;
  prior: Run | null;
}

interface Step {
  id: string;
  chapter: string;
  title: string;
  route: (d: TourData) => string;
  target?: string;
  body: (d: TourData) => ReactNode;
  action?: { label: string; run: () => void };
}

// The demo scene is a real dataset item: prism-core, analog clock, level 4, scene 4.
// Its first draw was rejected (hands overlapped), and Opus 5.5 misread it by one minute in the full run.
const DEMO_SCENE = "factory?family=clocks&difficulty=4&seed=2026&index=4";
const fam = (r: Run | null, f: string) => r?.metrics?.by_family[f]?.acc;
const modelRoute = (d: TourData, q = "") => (d.vlm ? `run/${d.vlm.id}${q}` : "runs");

const STEPS: Step[] = [
  {
    id: "intro", chapter: "The claim", title: "Visual tasks whose answers are proven, not assumed",
    route: () => "overview", target: "[data-tour=kpis]",
    body: (d) => (
      <>
        <p>Prism generates synthetic images and questions, and verifies every gold answer <b>twice</b>: from the scene that produced the image, and again from the <b>pixels alone</b> with an independent computer-vision verifier.</p>
        <p>These tiles are the evidence. Every shipped answer is cross-checked{d.evidence ? <>, and the verifier caught <b>{d.evidence.corruption_detection_pct}%</b> of {d.evidence.corruptions.toLocaleString()} deliberately corrupted labels</> : null}.</p>
      </>
    ),
  },
  {
    id: "scene", chapter: "1 · Generate", title: "One seeded scene, rendered deterministically",
    route: () => DEMO_SCENE, target: "[data-tour=stage]",
    body: () => (
      <>
        <p>This is item <code>clocks-d4-0004</code> from the benchmark: an analog clock at <b>level 4</b> (no numerals, 1-minute precision). It is a pure function of <code>(seed 2026, clocks, level 4, scene 4)</code>: rebuild it anywhere and the pixels are byte-identical.</p>
        <p>Each question shows the <b>gold</b> answer (from the scene) next to the <b>verified</b> answer (re-measured from the pixels). They must match, or the question never ships.</p>
      </>
    ),
  },
  {
    id: "trace", chapter: "2 · Validate", title: "Ambiguous scenes are rejected, with reasons",
    route: () => DEMO_SCENE, target: "[data-tour=trace]",
    body: () => (
      <>
        <p>The first draw for this cell put the hour and minute hands <b>closer than 20°</b>, which is ambiguous for a person, a model and the verifier alike, so the factory rejected it and drew again.</p>
        <p>The accepted draw then passed the determinism re-render, the pixel verifier, and the gold-vs-verified cross-check. Every rejection is counted per dataset.</p>
      </>
    ),
  },
  {
    id: "ask", chapter: "3 · Evaluate", title: "Ask Opus 5.5, live",
    route: () => DEMO_SCENE, target: "[data-tour=q0]",
    action: { label: "Ask the selected model", run: () => (document.querySelector("[data-tour=ask0]") as HTMLButtonElement | null)?.click() },
    body: () => (
      <>
        <p>Press the button to send this exact image and question to the selected model. The answer is parsed and graded on the spot.</p>
        <p>In the full benchmark run, Anthropic Opus 5.5 answered <b>11:52</b> here; the truth is <b>11:51</b>. That one-minute slip is the most common clock error: the model finds the hands but not their exact angle.</p>
      </>
    ),
  },
  {
    id: "variants", chapter: "3 · Evaluate", title: "Twins that isolate why a model fails",
    route: () => DEMO_SCENE, target: "[data-tour=variants]",
    body: () => (
      <>
        <p>Every base task gets controlled twins, and each changes exactly one thing:</p>
        <ul>
          <li><b>Paraphrase:</b> same pixels, reworded question → consistency.</li>
          <li><b>Perturbation:</b> degraded pixels, admitted only if the verifier still recovers the answer → robustness.</li>
          <li><b>Counterfactual:</b> a minimal edit that flips the answer → is the model actually looking?</li>
        </ul>
      </>
    ),
  },
  {
    id: "funnel", chapter: "4 · Scale", title: "A reproducible benchmark with an audit trail",
    route: () => "dataset/prism-core", target: "[data-tour=funnel]",
    body: () => (
      <>
        <p>The factory scales the same steps to a full dataset: <b>1,747 questions</b> across 6 families × 5 levels, built in about 30 seconds.</p>
        <p>The funnel shows every attempt that did not ship, and why: ambiguous scenes, verifier disagreements, duplicate content and near-duplicate images.</p>
      </>
    ),
  },
  {
    id: "balance", chapter: "4 · Scale", title: "The image is required",
    route: () => "dataset/prism-core", target: "[data-tour=balance]",
    body: (d) => (
      <>
        <p>Answers are balanced per template (yes/no is ~50/50), so the best <b>image-free</b> strategy, the majority answer per template, reaches only <b>{d.prior?.metrics ? pct(d.prior.metrics.overall.acc) : "~25%"}</b>.</p>
        <p>Low majority share and high entropy in this table mean a question cannot be answered from its wording alone.</p>
      </>
    ),
  },
  {
    id: "audit", chapter: "5 · Trust", title: "Auditing the verifier itself",
    route: () => "method", target: "[data-tour=audit]",
    body: (d) => (
      <>
        <p>A verifier that always says "agree" would make any dataset look perfect. So we <b>mutation-test</b> it: render an edited scene, claim the original labels, and check that it objects.</p>
        {d.evidence && <p>Result: <b>{d.evidence.corruption_detection_pct}%</b> of {d.evidence.corruptions.toLocaleString()} corruptions caught, <b>{d.evidence.agreement_pct}%</b> agreement on clean scenes, <b>{d.evidence.determinism_pct}%</b> deterministic renders.</p>}
        <p>A pixel-oracle model also answers every item through the same files, prompts and grader, and scores {d.oracle?.metrics ? pct(d.oracle.metrics.overall.acc) : "100%"}.</p>
      </>
    ),
  },
  {
    id: "score", chapter: "6 · Diagnose", title: "Opus 5.5 on the full benchmark",
    route: (d) => modelRoute(d), target: "[data-tour=run-kpis]",
    body: (d) => d.vlm?.metrics ? (
      <>
        <p>{d.vlm.label} scores <b>{pct(d.vlm.metrics.overall.acc)}</b> on {d.vlm.metrics.overall.n.toLocaleString()} questions (95% CI {pct(d.vlm.metrics.overall.lo)}–{pct(d.vlm.metrics.overall.hi)}), for ${d.vlm.metrics.usage.cost_usd.toFixed(2)}.</p>
        <p>It is <b>grounded</b>: right on both sides of {pct(d.vlm.metrics.counterfactual.grounded)} of counterfactual pairs, and "stuck" on only {pct(d.vlm.metrics.counterfactual.stuck)} (a blind model is stuck {d.prior?.metrics ? pct(d.prior.metrics.counterfactual.stuck) : "~90%"} of the time). Perturbations barely move it (flip rate {pct(d.vlm.metrics.robustness.flip_rate)}).</p>
      </>
    ) : <p>No Opus 5.5 run found yet. Start one from <b>Evaluations</b> (needs <code>ANTHROPIC_API_KEY</code>).</p>,
  },
  {
    id: "heat", chapter: "6 · Diagnose", title: "Where it breaks",
    route: (d) => modelRoute(d), target: "[data-tour=heat]",
    body: (d) => (
      <>
        <p>Turning up the difficulty knobs exposes the weak spots. Charts stay at <b>{pct(fam(d.vlm, "bars"), 0)}</b>, while analog clocks drop to <b>{pct(fam(d.vlm, "clocks"), 0)}</b> overall and lowest at level 4, where the numerals disappear.</p>
        <p>Tables hold until 7–10 rows; object counting holds until 14–19 objects.</p>
      </>
    ),
  },
  {
    id: "failures", chapter: "6 · Diagnose", title: "Every failure is inspectable",
    route: (d) => modelRoute(d, "?only=failures&family=mazes"), target: "[data-tour=items]",
    body: () => (
      <>
        <p>These are Opus 5.5's maze failures, with image, gold answer and parsed model answer. One pattern stands out: on every reachability miss Opus 5.5 says <b>"yes"</b> when the goal is actually <b>sealed off by walls</b>, a systematic optimism that only a verified, balanced benchmark makes visible.</p>
      </>
    ),
  },
  {
    id: "compare", chapter: "Wrap-up", title: "Floor, ceiling and the model in between",
    route: () => "compare", target: "[data-tour=compare]",
    body: () => (
      <>
        <p>Blind baselines set the floor, the pixel oracle sets the ceiling, and the gap shows what a vision model has to earn. Plug in any model (Opus 5.5, or any OpenAI-compatible VLM through Ollama or vLLM) and get the same diagnosis.</p>
        <p>Reproduce everything with <code>python -m prism build</code>, <code>verify</code>, <code>eval</code> and <code>serve</code>.</p>
      </>
    ),
  },
];

interface TourCtx {
  active: boolean;
  index: number;
  steps: Step[];
  data: TourData;
  start: (i?: number) => void;
  stop: () => void;
  goTo: (i: number) => void;
}

const Ctx = createContext<TourCtx | null>(null);
export const useTour = () => useContext(Ctx)!;

export function TourProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState(false);
  const [index, setIndex] = useState(0);
  const [data, setData] = useState<TourData>({ evidence: null, vlm: null, oracle: null, prior: null });

  useEffect(() => {
    if (!active) return;
    Promise.all([api.evidence().catch(() => null), api.runs().catch(() => [] as Run[])]).then(([ev, runs]) => {
      const done = runs.filter((r) => r.status === "done" && r.dataset === "prism-core" && r.metrics);
      // prefer the most complete run: largest item count first
      const bySize = [...done].sort((a, b) => (b.metrics!.overall.n ?? 0) - (a.metrics!.overall.n ?? 0));
      const pick = (p: (r: Run) => boolean) => bySize.find(p) ?? null;
      setData({
        evidence: ev?.summary ?? null,
        vlm: pick((r) => r.model === "anthropic:opus-5-5") ?? pick((r) => r.model.startsWith("anthropic:")),
        oracle: pick((r) => r.model === "oracle:pixels"),
        prior: pick((r) => r.model === "baseline:prior"),
      });
    });
  }, [active]);

  const start = useCallback((i = 0) => { setIndex(Math.max(0, Math.min(STEPS.length - 1, i))); setActive(true); }, []);
  const stop = useCallback(() => setActive(false), []);
  const goTo = useCallback((i: number) => setIndex(Math.max(0, Math.min(STEPS.length - 1, i))), []);
  const value = useMemo(() => ({ active, index, steps: STEPS, data, start, stop, goTo }), [active, index, data, start, stop, goTo]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Navigate to the step's deep link, wait for the target, spotlight it. */
function useSpotlight(step: Step | null, data: TourData, active: boolean, setDock: (d: "left" | "right") => void) {
  const prev = useRef<Element | null>(null);
  useEffect(() => {
    const clear = () => { prev.current?.classList.remove("tour-focus"); prev.current = null; };
    if (!active || !step) { clear(); return; }
    const want = "#/" + step.route(data);
    if (window.location.hash !== want) window.location.hash = want;
    let tries = 0;
    let timer = 0;
    const find = () => {
      const el = step.target ? document.querySelector(step.target) : null;
      if (el) {
        clear();
        el.classList.add("tour-focus");
        prev.current = el;
        const r = el.getBoundingClientRect();
        // put the target near the top so the narration panel never covers it,
        // and dock the panel on the side the target does not occupy
        window.scrollTo({ top: Math.max(0, r.top + window.scrollY - 28), behavior: "smooth" });
        setDock(r.left + r.width / 2 > window.innerWidth * 0.55 && r.width < window.innerWidth * 0.6 ? "left" : "right");
      } else if (tries++ < 40) {
        timer = window.setTimeout(find, 150);
      }
    };
    timer = window.setTimeout(find, 120);
    return () => window.clearTimeout(timer);
  }, [step, data, active, setDock]);
  useEffect(() => () => prev.current?.classList.remove("tour-focus"), []);
}

export function TourPanel() {
  const t = useTour();
  const step = t.active ? t.steps[t.index] : null;
  const [dock, setDock] = useState<"left" | "right">("right");
  useSpotlight(step, t.data, t.active, setDock);

  useEffect(() => {
    if (!t.active) return;
    const h = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (e.key === "ArrowRight") t.goTo(t.index + 1);
      else if (e.key === "ArrowLeft") t.goTo(t.index - 1);
      else if (e.key === "Escape") t.stop();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [t]);

  if (!step) return null;
  const last = t.index === t.steps.length - 1;
  return (
    <aside className={`tour ${dock}`} role="dialog" aria-label="Guided demo">
      <div className="tour-head">
        <span className="tour-chapter">{step.chapter}</span>
        <span className="tiny muted mono">{t.index + 1} / {t.steps.length}</span>
        <button className="btn ghost sm" onClick={t.stop} aria-label="Exit demo"><Icon.x /></button>
      </div>
      <div className="tour-progress">
        {t.steps.map((s, i) => (
          <button key={s.id} className={i === t.index ? "on" : i < t.index ? "done" : ""} onClick={() => t.goTo(i)} aria-label={`Step ${i + 1}: ${s.title}`} title={s.title} />
        ))}
      </div>
      <h3 className="tour-title">{step.title}</h3>
      <div className="tour-body">{step.body(t.data)}</div>
      {step.action && (
        <button className="btn sm" onClick={step.action.run} style={{ alignSelf: "flex-start" }}><Icon.play /> {step.action.label}</button>
      )}
      <div className="tour-foot">
        <button className="btn sm" disabled={t.index === 0} onClick={() => t.goTo(t.index - 1)}>Back</button>
        <span className="tiny muted">← → keys · Esc to exit</span>
        {last ? (
          <button className="btn sm primary" onClick={t.stop}>Finish</button>
        ) : (
          <button className="btn sm primary" onClick={() => t.goTo(t.index + 1)}>Next</button>
        )}
      </div>
    </aside>
  );
}
