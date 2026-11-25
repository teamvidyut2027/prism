// Typed client for the Prism FastAPI backend.

export type AnswerType = "integer" | "number" | "choice" | "boolean" | "time" | "sequence";

export interface Question {
  qid: string;
  template: string;
  text: string;
  answer_type: AnswerType;
  answer: unknown;
  verified_answer: unknown;
  verified: boolean;
  skills: string[];
  params: Record<string, unknown>;
  choices: string[] | null;
  tolerance: number;
  phrasing: number;
  instruction?: string;
}

export interface Task {
  task_id: string;
  family: string;
  seed: number;
  difficulty: number;
  scene: Record<string, unknown>;
  manifest: Record<string, unknown>;
  questions: Question[];
  variant: "base" | "paraphrase" | "perturbation" | "counterfactual";
  parent_id: string | null;
  variant_info: Record<string, any>;
  image_id: string;
  image_sha256: string;
  dhash: string;
  validation: Record<string, unknown>;
  width: number;
  height: number;
}

export interface Family {
  name: string;
  title: string;
  description: string;
  skills: string[];
  templates: Record<string, string>;
  knobs: Record<string, string>;
}

export interface Preview {
  family: string;
  difficulty: number;
  seed: number;
  index: number;
  elapsed_ms: number;
  events: Record<string, number>;
  examples: string[];
  tasks: Task[];
  images: Record<string, string>;
}

export interface Headline {
  tasks: number;
  base_tasks: number;
  questions: number;
  verified_pct: number;
  families: number;
  templates: number;
  prior_baseline_pct: number;
  boolean_true_pct: number | null;
}

export interface DatasetSummary {
  name: string;
  created: string;
  stats: Headline;
  config: Record<string, any>;
}

export interface DatasetMeta {
  name: string;
  created: string;
  build_seconds: number;
  config: Record<string, any>;
  funnel: Record<string, Record<string, number>>;
  rejection_examples: Record<string, string[]>;
  stats: {
    headline: Headline;
    by_family: Record<string, number>;
    grid: Record<string, Record<string, number>>;
    variants: Record<string, number>;
    templates: Record<string, number>;
    skills: Record<string, number>;
    answer_types: Record<string, number>;
    diversity: Record<string, { mean_dhash_distance: number; min_dhash_distance: number }>;
    answer_balance: Record<string, { distinct_answers: number; majority_share: number; entropy: number }>;
  };
}

export interface Cell {
  n: number;
  correct: number;
  acc: number | null;
  lo: number;
  hi: number;
}

export interface Metrics {
  overall: Cell & { base: Cell };
  by_family: Record<string, Cell>;
  by_difficulty: Record<string, Cell>;
  by_skill: Record<string, Cell>;
  by_answer_type: Record<string, Cell>;
  by_template: Record<string, Cell>;
  by_variant: Record<string, Cell>;
  by_perturbation: Record<string, Cell>;
  family_difficulty: Record<string, Record<string, Cell>>;
  consistency: { pairs: number; same_answer: number | null; both_correct: number | null };
  robustness: { pairs: number; clean_acc: number | null; perturbed_acc: number | null; flip_rate: number | null };
  counterfactual: { pairs: number; grounded: number | null; stuck: number | null };
  error_magnitude: Record<string, { mean: number; median: number; max: number; n: number }>;
  calibration?: { n: number; ece: number; brier: number; mean_confidence: number; bins: { bin: number; n: number; conf: number; acc: number }[] };
  usage: { input_tokens: number; output_tokens: number; cost_usd: number; latency_p50_ms: number | null; latency_p95_ms: number | null; errors: number; cached: number };
}

export interface Run {
  id: string;
  dataset: string;
  model: string;
  label: string;
  created: string;
  status: "running" | "done" | "failed";
  config: Record<string, any>;
  metrics: Metrics | null;
  summary?: Cell & { base: Cell };
  n_items: number;
  n_done: number;
  error: string | null;
}

export interface RunItem {
  qid: string;
  task_id: string;
  raw: unknown;
  parsed: unknown;
  correct: number;
  err: number | null;
  confidence: number | null;
  latency_ms: number;
  note: string;
  family: string;
  difficulty: number;
  variant: string;
  image_id: string;
  question: string;
  template: string;
  gold: unknown;
  answer_type: AnswerType;
  skills: string[];
  tolerance: number;
  variant_info: Record<string, any>;
}

export interface ModelInfo {
  id: string;
  label: string;
  kind: "vlm" | "baseline" | "oracle";
  blind: boolean;
  available: boolean;
  reason: string;
}

export interface Job {
  id: string;
  kind: string;
  status: "running" | "done" | "failed";
  done: number;
  total: number;
  detail: string;
  result: any;
  error: string | null;
  elapsed: number;
}

export interface Evidence {
  summary: {
    scenes: number;
    agreement_pct: number;
    determinism_pct: number;
    corruptions: number;
    corruption_detection_pct: number;
    per_family: Record<string, {
      scenes: number;
      agreement_pct: number;
      determinism_pct: number;
      corruptions: number;
      corruption_detection_pct: number;
      perturbation_recovery_pct: Record<string, number | null>;
    }>;
  };
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* not json */
    }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  families: () => req<Family[]>("/api/families"),
  preview: (family: string, difficulty: number, seed: number, index: number) =>
    req<Preview>(`/api/preview?family=${family}&difficulty=${difficulty}&seed=${seed}&index=${index}`),
  datasets: () => req<DatasetSummary[]>("/api/datasets"),
  dataset: (name: string) => req<DatasetMeta>(`/api/datasets/${encodeURIComponent(name)}`),
  datasetTasks: (name: string, q: Record<string, string | number | undefined>) => {
    const qs = Object.entries(q).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
    return req<{ total: number; items: Task[] }>(`/api/datasets/${encodeURIComponent(name)}/tasks?${qs}`);
  },
  buildDataset: (body: Record<string, unknown>) => req<Job>("/api/datasets", { method: "POST", body: JSON.stringify(body) }),
  models: () => req<ModelInfo[]>("/api/models"),
  runs: () => req<Run[]>("/api/runs"),
  run: (id: string) => req<Run>(`/api/runs/${encodeURIComponent(id)}`),
  runItems: (id: string, q: Record<string, string | number | undefined>) => {
    const qs = Object.entries(q).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
    return req<{ total: number; items: RunItem[] }>(`/api/runs/${encodeURIComponent(id)}/items?${qs}`);
  },
  deleteRun: (id: string) => req(`/api/runs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  startRun: (body: Record<string, unknown>) => req<Job>("/api/runs", { method: "POST", body: JSON.stringify(body) }),
  job: (id: string) => req<Job>(`/api/jobs/${id}`),
  ask: (body: Record<string, unknown>) =>
    req<{ raw: unknown; parsed: unknown; correct: boolean; error: string | null; gold: unknown; confidence: number | null; latency_ms: number; prompt: string }>(
      "/api/ask", { method: "POST", body: JSON.stringify(body) }),
  evidence: () => req<Evidence | null>("/api/evidence"),
};

export const imageUrl = (dataset: string, imageId: string) =>
  `/api/datasets/${encodeURIComponent(dataset)}/images/${encodeURIComponent(imageId)}.png`;

export function fmtAnswer(a: unknown): string {
  if (a === null || a === undefined) return "-";
  if (typeof a === "boolean") return a ? "yes" : "no";
  if (Array.isArray(a)) return a.join(" > ");
  return String(a);
}

export const pct = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "-" : `${(x * 100).toFixed(d)}%`);
