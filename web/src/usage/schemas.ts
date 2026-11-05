/** Zod shapes of the /api/tokens payloads (mirrors the old control-panel API; unknown keys are dropped). */
import { z } from "zod";

const number_ = z.number();
const maybe = z.number().nullable();
const text = z.string();
const maybeText = z.string().nullable();

export const banner = z.object({ level: z.enum(["green", "grey", "red"]), text });

export const tokensIndex = z.object({
  ab_banner: banner,
  coverage: z.object({
    aggregate_from: maybeText,
    any_from: maybeText,
    detail_from: maybeText,
    detail_to: maybeText,
    refreshed_at: number_,
    snapshots: z.array(text),
  }),
  options: z.object({ cwds: z.array(text), models: z.array(text) }),
  panels: z.array(z.object({ name: text, title: text })),
});
export type TokensIndex = z.infer<typeof tokensIndex>;

export const dailyRow = z.object({
  calls: number_,
  day: text,
  home_share: maybe,
  opus_share: maybe,
  over_share: maybe,
  sub_share: maybe,
  usd: number_,
  usd_per_call: maybe,
});
export type DailyRow = z.infer<typeof dailyRow>;

export const overviewPanel = z.object({
  daily: z.array(dailyRow),
  prompts: z.array(z.object({ day: text, prompts: number_ })),
  tiles: z.object({ active_h: number_, calls: number_, sessions: number_, usd: number_, usd_per_call: maybe, usd_per_day: number_ }),
  weekly: z.array(z.object({ calls: number_, usd: number_, week: text })),
});
export type OverviewPanel = z.infer<typeof overviewPanel>;

export const sessionRow = z.object({
  active_s: number_,
  calls: number_,
  cwd: maybeText,
  final_tag: maybeText,
  first_ts: number_,
  key: text,
  last_ts: number_,
  models: z.record(text, number_),
  prompts: number_,
  subagents: number_,
  title: text,
  usd: number_,
  usd_main: number_,
  usd_scope: number_.optional(),
  usd_sub: number_,
  wall_s: number_,
});
export type SessionRow = z.infer<typeof sessionRow>;

export const sessionsPanel = z.object({ sessions: z.array(sessionRow) });

const subagentRow = z.object({
  active_s: number_,
  agent_type: text,
  calls: number_,
  depth: number_,
  description: text,
  key: text,
  model: text,
  usd: number_,
  wall_s: number_,
});
export type SubagentRow = z.infer<typeof subagentRow>;

const toolRow = z.object({ calls: number_, carry_usd: number_, name: text, result_tokens: number_, share: maybe, usd: number_ });
export type ToolRow = z.infer<typeof toolRow>;

const promptRow = z.object({
  active_s: number_,
  calls: number_,
  idx: number_,
  subagents: z.array(subagentRow),
  text,
  tools: z.array(toolRow),
  ts: number_,
  usd: number_,
  usd_own: number_,
  usd_sub: number_,
  wall_s: number_,
});
export type PromptRow = z.infer<typeof promptRow>;

export const sessionDetail = z.object({
  prompts: z.array(promptRow),
  session: sessionRow,
  unattributed: z.array(subagentRow),
});
export type SessionDetail = z.infer<typeof sessionDetail>;

const breach = z.object({ hard: z.boolean(), limit: number_, measure: text, value: number_, why: text });
const contextFile = z.object({
  breaches: z.array(breach),
  budgets: z.array(text),
  bytes: maybe,
  history: z.array(z.object({ bytes: number_, source: text, ts: number_ })),
  kind: text,
  lines: maybe,
  path: text,
  standing: text,
  status: z.enum(["ok", "over budget", "over hard limit"]),
  tokens: number_,
  usd_per_day: number_,
  warning: maybeText,
});
export type ContextFile = z.infer<typeof contextFile>;

export const contextPanel = z.object({
  calls_per_day: number_,
  files: z.array(contextFile),
  measure_command: text,
  price_per_mtok: number_,
});
export type ContextPanel = z.infer<typeof contextPanel>;

export const contextFileDetail = z.object({
  content: maybeText,
  git_log: z.array(text),
  kind: text,
  path: text,
});
export type ContextFileDetail = z.infer<typeof contextFileDetail>;
