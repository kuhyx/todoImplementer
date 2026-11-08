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
  "spec", "spec_wait", "plan", "implement", "live_check", "checks", "gate", "shipping", "shipped", "failed", "paused_limit",
  "cancelled",
] as const;
export const STATUSES = [
  "backlog", "yours", "cancelled", "queued", "working", "paused_limit", "shipping", "needs_you", "ready_to_ship",
  "done",
] as const;
export const COLUMN_IDS = ["backlog", "running", "needs_you", "ready", "done"] as const;
export const NEEDS_KINDS = [
  "spec_questions", "spec_ok", "claude_question", "claude_action", "checks_failed", "run_failed", "handed_to_you",
] as const;
export const ACTION_IDS = [
  "start", "spec-answers", "spec-ok", "send", "ship", "cancel", "credits", "lesson-approve", "copy-resume",
] as const;

export const stage = z.enum(STAGES);
export const status = z.enum(STATUSES);
export const column = z.enum(COLUMN_IDS);

export const needs = z
  .strictObject({ kind: z.enum(NEEDS_KINDS), text: z.string().min(1) })
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

export const limit = z.strictObject({
  active: z.boolean(),
  credits_available: z.boolean(),
  until: epoch.nullable(),
});

export const apiError = z.strictObject({
  code: z.enum(["bad_request", "forbidden", "not_found", "disabled", "conflict", "internal"]),
  message: z.string().min(1),
});

export const taskCard = z.strictObject({
  actions,
  assignee: z.enum(["human", "claude"]),
  column,
  cost_usd: usd,
  current: z.string(),
  id: itemId,
  needs,
  priority: z.string(),
  repo: z.string().nullable(),
  resumes_at: epoch.nullable(),
  stage: stage.nullable(),
  status,
  title: z.string().min(1),
  updated: epoch.nullable(),
});

export type Action = z.infer<typeof action>;
export type ActionOption = z.infer<typeof actionOption>;
export type Question = z.infer<typeof question>;
export type TaskCard = z.infer<typeof taskCard>;
export type ColumnId = z.infer<typeof column>;
export type Status = z.infer<typeof status>;

export type ActionId = (typeof ACTION_IDS)[number];
