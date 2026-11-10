/**
 * Zod mirrors of contracts/common.schema.json. The JSON Schemas are the
 * source of truth; contracts.test.ts runs both over the same fixtures so a
 * drift fails a test instead of the page.
 */
import { z } from "zod";

/** Card id: `<note id8>-<index of the note's ## section>`. */
export const itemId = z.string().regex(/^[A-Za-z0-9]{8}-\d+$/);
export const epoch = z.number().min(0);
export const usd = z.number().min(0);

export const STAGES = [
  "spec", "spec_wait", "plan", "implement", "live_check", "checks", "gate", "shipping", "shipped", "closing", "closed",
  "failed", "paused_limit", "paused_retry", "cancelled",
] as const;
export const STATUSES = [
  "backlog", "yours", "cancelled", "queued", "working", "paused_limit", "shipping", "needs_you", "ready_to_ship",
  "ready_to_close", "done",
] as const;
export const COLUMN_IDS = ["backlog", "running", "needs_you", "ready", "done"] as const;
export const NEEDS_KINDS = [
  "spec_questions", "spec_ok", "claude_question", "claude_action", "phone", "checks_failed", "run_failed", "handed_to_you", "permission",
] as const;
export const ACTION_IDS = [
  "start", "spec-answers", "spec-ok", "send", "ship", "close", "cancel", "lesson-approve", "copy-resume", "go", "copy-fix",
  "rerun",
] as const;

export const stage = z.enum(STAGES);
export const status = z.enum(STATUSES);
export const column = z.enum(COLUMN_IDS);

export const NEEDS_CATEGORIES = ["questions", "criteria", "action", "auto", "phone", "permission"] as const;

export const needs = z
  .strictObject({
    category: z.enum(NEEDS_CATEGORIES),
    command: z.string().min(1).optional(),
    effort: z.number().int().min(1),
    kind: z.enum(NEEDS_KINDS),
    text: z.string().min(1),
  })
  .nullable();

export const partial = z
  .strictObject({
    deferred: z.array(z.string()),
    done: z.array(z.string()),
    followup_id: z.string().nullable(),
    open: z.array(z.string()),
  })
  .nullable();

const hasReason = (a: { enabled: boolean; reason: null | string }): boolean => a.enabled || (a.reason !== null && a.reason.length > 0);

/** A checkbox sent with its action's click (Start/Restart: auto_ship). */
export const actionOption = z
  .strictObject({ enabled: z.boolean(), id: z.enum(["auto_ship"]), label: z.string().min(1), reason: z.string().nullable() })
  .refine(hasReason, { message: "a disabled option needs a reason" });

export const action = z
  .strictObject({
    confirm: z.boolean().optional(),
    enabled: z.boolean(),
    id: z.enum(ACTION_IDS),
    label: z.string().min(1),
    option: actionOption.optional(),
    reason: z.string().nullable(),
    value: z.string().optional(),
  })
  .refine(hasReason, { message: "a disabled action needs a reason" });
export const actions = z.array(action);

export const question = z.strictObject({
  answer: z.string().nullable(),
  body: z.string(),
  id: z.string().regex(/^Q\d+$/),
  recommendation: z.string(),
  title: z.string().min(1),
});

export const checks = z.strictObject({
  log: z.string().optional(),
  passed: z.boolean(),
  ran_at: epoch,
  results: z.array(z.strictObject({ command: z.string().min(1), exit: z.number().int(), tail: z.string() })),
});

export const liveCheck = z.strictObject({ report_md: z.string(), shots: z.array(z.string()) });

export const selfCheck = z.array(
  z.strictObject({ criterion: z.string().min(1), done: z.boolean(), note: z.string().optional() }),
);

export const lesson = z.strictObject({
  evidence: z.string(),
  id: z.string().min(1),
  mistake: z.string(),
  rule: z.string(),
  skill: z.string().min(1),
  state: z.enum(["drafted", "approved", "rejected"]),
});

/** The free API credits fallback, worded by the server (common.schema.json $defs/credits). */
export const credits = z.strictObject({
  enabled: z.boolean(),
  state: z.enum(["off", "ready", "exhausted", "unavailable"]),
  text: z.string().min(1),
});

export const limit = z.strictObject({
  active: z.boolean(),
  credits,
  until: epoch.nullable(),
});

export const apiError = z.strictObject({
  code: z.enum(["bad_request", "forbidden", "not_found", "disabled", "conflict", "internal"]),
  message: z.string().min(1),
});

/** Cheap-tier badges, decided by the server (common.schema.json $defs/tier_badges). */
export const tierFlags = z.strictObject({ cheap: z.boolean(), escalated: z.boolean(), free: z.boolean() });

/** Umbrella card progress (common.schema.json $defs/umbrella_counts): children per bucket, next round width, issues. */
export const umbrellaCounts = z.strictObject({
  done: z.number().int().min(0),
  failed: z.number().int().min(0),
  issues: z.number().int().min(0),
  queued: z.number().int().min(0),
  ready: z.number().int().min(0),
  round: z.number().int().min(0),
  running: z.number().int().min(0),
  total: z.number().int().min(0),
  width: z.number().int().min(1),
});

/** Set when a passing done_check started the run (a closing run); kept after Close. */
export const autoStart = z.strictObject({ passed_at: epoch, reason: z.literal("done_check") });

/** One part of a repo task (repotask.schema.json $defs/part): its state and, when split, the sub-step counts. */
export const PART_STATES = ["todo", "working", "done", "human", "held"] as const;
export const repoPart = z.strictObject({
  id: itemId,
  state: z.enum(PART_STATES),
  steps: z.strictObject({ done: z.number().int().min(0), total: z.number().int().min(1) }).nullable(),
  title: z.string().min(1),
});

export const taskCard = z.strictObject({
  actions,
  assignee: z.enum(["human", "claude"]),
  auto: z.string().nullable(),
  auto_start: autoStart.nullable(),
  column,
  cost_usd: usd,
  current: z.string(),
  id: itemId,
  needs,
  partial,
  parts: z.array(repoPart).optional(),
  priority: z.string(),
  repo: z.string().nullable(),
  resumes_at: epoch.nullable(),
  route: z.enum(["plan", "credits"]).nullable(),
  stage: stage.nullable(),
  status,
  tier: tierFlags,
  title: z.string().min(1),
  umbrella: umbrellaCounts.optional(),
  updated: epoch.nullable(),
  waits_on: itemId.nullable().optional(),
});

export type Action = z.infer<typeof action>;
export type ActionOption = z.infer<typeof actionOption>;
export type Credits = z.infer<typeof credits>;
export type Question = z.infer<typeof question>;
export type RepoPart = z.infer<typeof repoPart>;
export type TaskCard = z.infer<typeof taskCard>;
export type UmbrellaCounts = z.infer<typeof umbrellaCounts>;
export type NeedsCategory = (typeof NEEDS_CATEGORIES)[number];
export type ColumnId = z.infer<typeof column>;
export type Status = z.infer<typeof status>;

export type ActionId = (typeof ACTION_IDS)[number];
