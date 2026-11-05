/** Zod shapes for the levers, anomalies, A/B, efficiency, items and generic panels. */
import { z } from "zod";

import { banner } from "@/usage/schemas";

const number_ = z.number();
const maybe = z.number().nullable();
const text = z.string();
const maybeText = z.string().nullable();

const leverRow = z.object({
  actual: maybe,
  baseline: maybe,
  date: maybeText,
  detail: maybeText,
  lever: text,
  lower_is_better: number_,
  metric: text,
  outcome: maybeText,
  predicted: maybe,
  source: text,
  status: z.enum(["applied", "not applied", "proposed"]),
});
export type LeverRow = z.infer<typeof leverRow>;

const point = z.object({ date: text, value: maybe });
export type MetricPoint = z.infer<typeof point>;

export const leversPanel = z.object({
  rolling_days: number_,
  rows: z.array(leverRow),
  series: z.record(text, z.object({ daily: z.array(point), snapshots: z.array(point) })),
});
export type LeversPanel = z.infer<typeof leversPanel>;

export const anomaliesPanel = z.object({
  caption: text,
  categories: z.array(z.object({ calls: number_, category: text, cost_usd: number_, key: text })),
  category_totals: z.array(z.object({ calls: number_, category: text, cost_usd: number_ })),
  expensive: z.array(z.object({ calls: number_, cwd: maybeText, day: text, key: text, title: text, usd: number_ })),
  loops: z.array(z.object({ cost_usd: number_, key: text, name: text, repeats: number_, target: text })),
  over: number_,
  spikes: z.array(z.object({ day: text, median_usd: number_, ratio: maybe, usd: number_ })),
  totals: z.object({ expensive: number_, expensive_usd: number_, loops: number_, spikes: number_ }),
});
export type AnomaliesPanel = z.infer<typeof anomaliesPanel>;

const rateCi = z.object({ high: number_, k: number_, low: number_, rate: maybe });
const meanCi = z.object({ high: number_, low: number_, mean: number_ });
const arm = z.object({
  correction: rateCi,
  duration_s: meanCi,
  error: rateCi,
  followup: rateCi,
  n: number_,
  redo: rateCi,
  tags: z.record(text, number_),
  usd: meanCi,
});
export type AbArm = z.infer<typeof arm>;

const experiment = z.object({
  arms: z.record(text, arm),
  banner,
  diffs: z.record(text, z.object({ diff: number_, high: number_, low: number_ })).optional(),
  metrics: z.array(z.object({ difference: text, measure: text, opus: text, sonnet: text })).optional(),
  unjoined: number_.optional(),
});
export type AbExperiment = z.infer<typeof experiment>;

export const abPanel = experiment.extend({ build: experiment.optional() });
export type AbPanel = z.infer<typeof abPanel>;

const weekRow = z.record(text, z.union([z.number(), z.string()]).nullable());
export type WeekRow = z.infer<typeof weekRow>;

export const efficiencyPanel = z.object({
  captions: z.record(text, text),
  commits: z.array(weekRow),
  done: z.array(weekRow),
  estimate: z.array(weekRow),
  notes: z.array(weekRow).optional(),
  notes_weekly: z.array(weekRow).optional(),
});
export type EfficiencyPanel = z.infer<typeof efficiencyPanel>;

const costRow = { calls: number_, sessions: number_, usd: number_ };

/** GET /api/tokens/items: one row per item and stage, plus the same cost rolled up per repo and per stage. */
export const itemsPanel = z.object({
  items: z.array(z.object({ ...costRow, item: text, repo: text, stage: text })),
  repos: z.array(z.object({ ...costRow, repo: text })),
  stages: z.array(z.object({ ...costRow, stage: text })),
  total_usd: number_,
});
export type ItemsPanel = z.infer<typeof itemsPanel>;

/** Any other panel: every top-level array of objects becomes a generic table. */
export const genericPanel = z.record(text, z.unknown());
export type GenericPanel = z.infer<typeof genericPanel>;
