import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, pct, type Cell, type Job } from "../api";
import { Icon } from "./icons";

export function Card(p: { title?: ReactNode; sub?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; pad?: boolean; tour?: string }) {
  return (
    <section className={`card ${p.className ?? ""}`} data-tour={p.tour}>
      {(p.title || p.right) && (
        <div className="card-head">
          <div>
            {p.title && <h2>{p.title}</h2>}
            {p.sub && <div className="sub">{p.sub}</div>}
          </div>
          {p.right}
        </div>
      )}
      <div className={p.pad === false ? "" : "card-body"}>{p.children}</div>
    </section>
  );
}

export function Kpi(p: { label: ReactNode; value: ReactNode; hint?: ReactNode; tone?: "good" | "bad"; accent?: boolean }) {
  return (
    <div className={`card kpi ${p.accent ? "accent" : ""}`}>
      <div className="label">{p.label}</div>
      <div className={`value ${p.tone ?? ""}`}>{p.value}</div>
      {p.hint && <div className="hint">{p.hint}</div>}
    </div>
  );
}

export function Badge(p: { tone?: "good" | "bad" | "warn" | "accent"; children: ReactNode; title?: string }) {
  return <span className={`badge ${p.tone ?? ""}`} title={p.title}>{p.children}</span>;
}

export function Verified({ ok, label }: { ok: boolean; label?: string }) {
  return ok ? (
    <Badge tone="good" title="Gold answer reproduced independently from the rendered pixels"><Icon.check /> {label ?? "verified"}</Badge>
  ) : (
    <Badge tone="bad"><Icon.x /> {label ?? "unverified"}</Badge>
  );
}

export function Seg<T extends string | number>(p: { value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void }) {
  return (
    <div className="seg" role="tablist">
      {p.options.map((o) => (
        <button key={String(o.value)} className={o.value === p.value ? "on" : ""} onClick={() => p.onChange(o.value)} role="tab" aria-selected={o.value === p.value}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function AccBar({ c, color }: { c: Cell | undefined; color?: string }) {
  if (!c || c.acc === null) return <span className="muted">-</span>;
  return (
    <div className="accbar" title={`${c.correct}/${c.n} · 95% CI ${pct(c.lo)}–${pct(c.hi)}`}>
      <div className="track">
        <div className="ci" style={{ left: `${c.lo * 100}%`, width: `${(c.hi - c.lo) * 100}%` }} />
        <div className="fill" style={{ width: `${c.acc * 100}%`, background: color }} />
      </div>
      <span className="strong" style={{ minWidth: 48, textAlign: "right" }}>{pct(c.acc)}</span>
    </div>
  );
}

export function Empty(p: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <h3>{p.title}</h3>
      <div>{p.children}</div>
    </div>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  return error ? <div className="err">{error}</div> : null;
}

export function Modal(p: { title: ReactNode; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && p.onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [p]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && p.onClose()}>
      <div className="modal" role="dialog" aria-modal="true">
        <div className="modal-head">
          <h2>{p.title}</h2>
          <button className="btn ghost sm" onClick={p.onClose} aria-label="Close"><Icon.x /></button>
        </div>
        <div style={{ padding: 18 }}>{p.children}</div>
      </div>
    </div>
  );
}

/** Poll a background job until it finishes. */
export function useJob(onDone?: (j: Job) => void) {
  const [job, setJob] = useState<Job | null>(null);
  const timer = useRef<number | null>(null);
  const cb = useRef(onDone);
  cb.current = onDone;
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);
  const track = (j: Job) => {
    setJob(j);
    const tick = async () => {
      try {
        const n = await api.job(j.id);
        setJob(n);
        if (n.status === "running") timer.current = window.setTimeout(tick, 700);
        else cb.current?.(n);
      } catch {
        timer.current = window.setTimeout(tick, 1500);
      }
    };
    timer.current = window.setTimeout(tick, 500);
  };
  return { job, track, clear: () => setJob(null) };
}

export function JobBar({ job }: { job: Job | null }) {
  if (!job) return null;
  const p = job.total ? job.done / job.total : 0;
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row between small">
        <span className="row" style={{ gap: 8 }}>
          {job.status === "running" && <span className="spinner" />}
          <span className="strong">{job.status === "running" ? (job.kind === "build" ? "Building dataset" : "Evaluating") : job.status === "done" ? "Finished" : "Failed"}</span>
          <span className="muted">{job.detail}</span>
        </span>
        <span className="muted mono">{job.done}/{job.total || "?"} · {job.elapsed}s</span>
      </div>
      <div className="progress"><div style={{ width: `${(job.status === "done" ? 1 : p) * 100}%` }} /></div>
      <ErrorBox error={job.error} />
    </div>
  );
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: true });
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    fn().then(
      (data) => alive && setState({ data, error: null, loading: false }),
      (e: Error) => alive && setState({ data: null, error: e.message, loading: false }),
    );
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);
  return { ...state, reload: () => setNonce((n) => n + 1) };
}

export const famTitle: Record<string, string> = {
  bars: "Bar charts", lines: "Line charts", shapes: "Object scenes", clocks: "Analog clocks", mazes: "Grid mazes", tables: "Data tables",
};

export const skillTitle = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
