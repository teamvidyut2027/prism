// Small, dependency-free SVG charts tuned for this dashboard.
import { useMemo, useState } from "react";
import { pct, type Cell } from "../api";

export const SERIES = ["#6d5efc", "#0fb5c2", "#f59e0b", "#e0457b", "#22a35a", "#3b82f6", "#a855f7", "#64748b"];

/** Horizontal bars with 95% CI whiskers. rows: label -> cells per series. */
export function HBars(p: { rows: { label: string; cells: (Cell | undefined)[] }[]; series: string[]; height?: number }) {
  const rowH = 22 * Math.max(1, p.series.length) + 14;
  const W = 640, L = 150, R = 56;
  const H = p.rows.length * rowH + 26;
  const x = (v: number) => L + v * (W - L - R);
  return (
    <div>
      {p.series.length > 1 && <Legend items={p.series} />}
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img">
        <g className="grid">
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={0} y2={H - 20} />
              <text x={x(t)} y={H - 6} textAnchor="middle">{t * 100}%</text>
            </g>
          ))}
        </g>
        {p.rows.map((r, i) => (
          <g key={r.label} transform={`translate(0 ${i * rowH + 6})`}>
            <text className="lbl" x={L - 10} y={(rowH - 14) / 2 + 4} textAnchor="end">{r.label}</text>
            {r.cells.map((c, j) => {
              if (!c || c.acc === null) return null;
              const y = j * 22;
              const col = SERIES[j % SERIES.length];
              return (
                <g key={j}>
                  <title>{`${p.series[j] ?? ""} ${r.label}: ${pct(c.acc)} (${c.correct}/${c.n}), 95% CI ${pct(c.lo)}–${pct(c.hi)}`}</title>
                  <rect x={L} y={y} width={Math.max(1, x(c.acc) - L)} height={16} rx={4} fill={col} opacity={0.9} />
                  <line x1={x(c.lo)} x2={x(c.hi)} y1={y + 8} y2={y + 8} stroke="var(--text)" strokeOpacity={0.55} strokeWidth={1.4} />
                  <line x1={x(c.lo)} x2={x(c.lo)} y1={y + 4} y2={y + 12} stroke="var(--text)" strokeOpacity={0.55} strokeWidth={1.4} />
                  <line x1={x(c.hi)} x2={x(c.hi)} y1={y + 4} y2={y + 12} stroke="var(--text)" strokeOpacity={0.55} strokeWidth={1.4} />
                  <text className="val" x={W - R + 8} y={y + 12}>{pct(c.acc, 0)}</text>
                </g>
              );
            })}
          </g>
        ))}
      </svg>
    </div>
  );
}

/** Lines over an ordinal x axis (e.g. difficulty 1..5). */
export function LineChart(p: { xs: (string | number)[]; series: { name: string; values: (number | null)[] }[]; yLabel?: string; height?: number }) {
  const W = 640, H = p.height ?? 260, L = 44, R = 16, T = 12, B = 30;
  const x = (i: number) => L + (p.xs.length === 1 ? 0.5 : i / (p.xs.length - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - v) * (H - T - B);
  const [hover, setHover] = useState<number | null>(null);
  return (
    <div>
      <Legend items={p.series.map((s) => s.name)} />
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} width="100%" onMouseLeave={() => setHover(null)}>
        <g className="grid">
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <g key={t}>
              <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} />
              <text x={L - 8} y={y(t) + 4} textAnchor="end">{t * 100}%</text>
            </g>
          ))}
        </g>
        {p.xs.map((v, i) => (
          <g key={i}>
            <text x={x(i)} y={H - 10} textAnchor="middle">{v}</text>
            <rect x={x(i) - 20} y={T} width={40} height={H - T - B} fill="transparent" onMouseEnter={() => setHover(i)} />
          </g>
        ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="var(--border-strong)" strokeDasharray="3 3" />}
        {p.series.map((s, k) => {
          const col = SERIES[k % SERIES.length];
          const pts = s.values.map((v, i) => (v === null ? null : [x(i), y(v)] as const));
          const d = pts.reduce((acc, pt, i) => (pt ? acc + `${acc && pts[i - 1] ? "L" : "M"}${pt[0]},${pt[1]}` : acc), "");
          return (
            <g key={s.name}>
              <path d={d} fill="none" stroke={col} strokeWidth={2.4} strokeLinejoin="round" />
              {pts.map((pt, i) => pt && (
                <circle key={i} cx={pt[0]} cy={pt[1]} r={hover === i ? 5 : 3.5} fill="var(--panel)" stroke={col} strokeWidth={2}>
                  <title>{`${s.name} @ ${p.xs[i]}: ${pct(s.values[i])}`}</title>
                </circle>
              ))}
              {hover !== null && s.values[hover] !== null && (
                <text x={x(hover) + 8} y={y(s.values[hover] as number) - 6} className="val" fill={col}>{pct(s.values[hover], 0)}</text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function Legend({ items }: { items: string[] }) {
  return (
    <div className="legend" style={{ marginBottom: 8 }}>
      {items.map((s, i) => (
        <span key={s}><i style={{ background: SERIES[i % SERIES.length] }} />{s}</span>
      ))}
    </div>
  );
}

/** Accuracy heatmap: rows x cols of cells. */
export function Heatmap(p: { rows: string[]; cols: string[]; get: (r: string, c: string) => Cell | undefined; rowLabel?: (r: string) => string; colLabel?: (c: string) => string }) {
  // red (0%) -> amber (50%) -> green (100%), translucent so text stays readable in both themes
  const color = (a: number) => `hsl(${Math.round(a * 135)} 72% 47% / 0.34)`;
  return (
    <div className="table-wrap">
      <table className="heat">
        <thead>
          <tr>
            <th />
            {p.cols.map((c) => <th key={c}>{p.colLabel ? p.colLabel(c) : c}</th>)}
          </tr>
        </thead>
        <tbody>
          {p.rows.map((r) => (
            <tr key={r}>
              <th className="rowh">{p.rowLabel ? p.rowLabel(r) : r}</th>
              {p.cols.map((c) => {
                const cell = p.get(r, c);
                if (!cell || cell.acc === null) return <td key={c} style={{ background: "var(--heat-0)" }} className="muted">·</td>;
                return (
                  <td key={c} style={{ background: color(cell.acc), color: "var(--text)" }} title={`${cell.correct}/${cell.n} · 95% CI ${pct(cell.lo)}–${pct(cell.hi)}`}>
                    {Math.round(cell.acc * 100)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Reliability diagram (calibration). */
export function Reliability(p: { bins: { bin: number; n: number; conf: number; acc: number }[] }) {
  const W = 300, H = 260, L = 40, B = 30, T = 10, R = 10;
  const sx = (v: number) => L + v * (W - L - R);
  const sy = (v: number) => T + (1 - v) * (H - T - B);
  const maxN = useMemo(() => Math.max(1, ...p.bins.map((b) => b.n)), [p.bins]);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: 380 }}>
      <g className="grid">
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line x1={sx(0)} x2={sx(1)} y1={sy(t)} y2={sy(t)} />
            <text x={L - 6} y={sy(t) + 4} textAnchor="end">{t * 100}%</text>
            <text x={sx(t)} y={H - 10} textAnchor="middle">{t * 100}%</text>
          </g>
        ))}
      </g>
      <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="var(--border-strong)" strokeDasharray="4 4" />
      {p.bins.map((b) => (
        <g key={b.bin}>
          <rect x={sx(b.bin) + 2} y={sy(b.acc)} width={(W - L - R) / 10 - 4} height={sy(0) - sy(b.acc)} rx={3} fill="#6d5efc" opacity={0.25 + 0.65 * (b.n / maxN)}>
            <title>{`confidence ${pct(b.conf)} → accuracy ${pct(b.acc)} (n=${b.n})`}</title>
          </rect>
        </g>
      ))}
      <text x={sx(0.5)} y={T + 12} textAnchor="middle">stated confidence → observed accuracy</text>
    </svg>
  );
}

/** Stacked horizontal funnel bar. */
export function StackBar(p: { parts: { label: string; value: number; color: string }[] }) {
  const total = p.parts.reduce((a, b) => a + b.value, 0) || 1;
  return (
    <div>
      <div style={{ display: "flex", height: 12, borderRadius: 99, overflow: "hidden", background: "var(--panel-3)" }}>
        {p.parts.filter((x) => x.value > 0).map((x) => (
          <div key={x.label} title={`${x.label}: ${x.value}`} style={{ width: `${(x.value / total) * 100}%`, background: x.color }} />
        ))}
      </div>
    </div>
  );
}
