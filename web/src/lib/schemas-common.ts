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
  "failed", "paused_limit", "paused_retry", "cancelled", "done_manually",
] as const;
export const STATUSES = [
  "backlog", "yours", "cancelled", "queued", "working", "paused_limit", "shipping", "waiting_phone_update", "needs_you",
  "done", "done_manually",
] as const;
export const COLUMN_IDS = ["backlog", "running", "needs_you", "done"] as const;
export const NEEDS_KINDS = [
  "spec_questions", "spec_ok", "claude_question", "claude_action", "phone", "checks_failed", "run_failed", "handed_to_you", "permission",
] as const;
export const ACTION_IDS = [
  "start", "spec-answers", "spec-ok", "send", "ship", "close", "cancel", "lesson-approve", "copy-resume", "go", "copy-fix",
  "rerun", "wont", "done-manually", "model", "priority",
] as const;
export const LANES = ["kuhy", "board", "app"] as const; // who asked: kuhy, the board, other apps' reports (T2580)

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
    links: z.array(z.string().regex(/^https?:\/\/\S+$/)).min(1).max(5).optional(),
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

/** One row of the model picker: the id the click sends, a short name. */
export const actionChoice = z.strictObject({
  id: z.string().min(1),
  label: z.string().min(1),
  note: z.literal("default").optional(), // the model the roles run unpinned (T2470)
});

/** Start only (T2583): the higher-priority Backlog card a click would jump; the drawer asks first (priority.schema.json). */
export const actionWaits = z.strictObject({ id: itemId, priority: z.string(), title: z.string().min(1) });

export const action = z
  .strictObject({
    choices: z.array(actionChoice).min(1).optional(),
    confirm: z.boolean().optional(),
    enabled: z.boolean(),
    id: z.enum(ACTION_IDS),
    label: z.string().min(1),
    option: actionOption.optional(),
    reason: z.string().nullable(),
    value: z.string().optional(),
    waits: actionWaits.optional(),
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

/** The paced free API credits, worded and computed by the server (credits.schema.json $defs/credits). */
export const credits = z.strictObject({
  batches: z.strictObject({ est_usd: usd, oldest_at: epoch.nullable(), pending: z.number().int().nonnegative() }),
  cap_usd: usd,
  cost_factor: z.number().positive(),
  credit_turns_period: z.number().int().nonnegative(),
  enabled: z.boolean(),
  monthly_usd: usd,
  over_cap: z.boolean(),
  period_start: epoch,
  remaining_usd: usd,
  route: z.enum(["plan", "credits"]).nullable(),
  running_credit_turns: z.number().int().nonnegative(),
  spent_period_usd: usd,
  state: z.enum(["off", "ready", "exhausted", "unavailable"]),
  text: z.string().min(1),
  week: z.number().int().min(1).max(4),
});

export const limit = z.strictObject({
  active: z.boolean(),
  credits,
  until: epoch.nullable(),
  weekly_hold: z.enum(["none", "low_medium", "all"]),
  weekly_used: z.number().nonnegative().nullable(),
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
  round: z.number().int().min(0),
  running: z.number().int().min(0),
  total: z.number().int().min(0),
  width: z.number().int().min(1),
});

/** Set when a passing done_check started the run (a closing run); kept after Close. */
export const autoStart = z.strictObject({ passed_at: epoch, reason: z.literal("done_check") });

/** One part of a repo task (repotask.schema.json $defs/part): its state and, when split, the sub-step counts. */
export const PART_STATES = ["todo", "working", "done", "human", "held"] as const;
/** Whether kuhy may edit the part now (856c0f0a); a disabled one says why. */
export const partEdit = z.union([z.strictObject({ enabled: z.literal(true), reason: z.null() }), z.strictObject({ enabled: z.literal(false), reason: z.string().min(1) })]);
export const repoPart = z.strictObject({
  /** The part's own text: only in GET /api/task, the editor's start value. */
  body: z.string().optional(),
  edit: partEdit,
  id: itemId,
  state: z.enum(PART_STATES),
  steps: z.strictObject({ done: z.number().int().min(0), total: z.number().int().min(1) }).nullable(),
  title: z.string().min(1),
  /** The note's own title with its image markdown, the editor's start value (T2614). */
  title_source: z.string().min(1).optional(),
});

/** What triage decided about a note that had no repo (common.schema.json task_card.triage). */
export const TRIAGE_LABELS = ["new_repo", "existing_repo", "all_repos", "research", "manual"] as const;

/** A todo-image the note links (T2535); GET /api/image/<folder>/<file> serves it. */
export const noteImage = z.strictObject({ file: z.string().regex(/^[\w-]+\.[a-z0-9]{1,10}$/), folder: z.string().regex(/^[\w-]+$/) });
export type NoteImage = z.infer<typeof noteImage>;

export const taskCard = z.strictObject({
  actions,
  app_error: z.number().int().min(1).optional(),
  assignee: z.enum(["human", "claude"]),
  auto: z.string().nullable(),
  auto_start: autoStart.nullable(),
  column,
  cost_usd: usd,
  current: z.string(),
  id: itemId,
  images: z.array(noteImage).min(1).optional(),
  lane: z.enum(LANES),
  needs,
  partial,
  parts: z.array(repoPart).optional(),
  priority: z.string(),
  repo: z.string().nullable(),
  resumes_at: epoch.nullable(),
  route: z.enum(["plan", "credits", "free"]).nullable(),
  stage: stage.nullable(),
  status,
  tier: tierFlags,
  title: z.string().min(1),
  triage: z.enum(TRIAGE_LABELS).optional(),
  umbrella: umbrellaCounts.optional(),
  updated: epoch.nullable(),
  waits_on: itemId.nullable().optional(),
});

export type ActionWaits = z.infer<typeof actionWaits>;
export type Action = z.infer<typeof action>;
export type ActionOption = z.infer<typeof actionOption>;
export type ActionChoice = z.infer<typeof actionChoice>;
export type Credits = z.infer<typeof credits>;
export type Question = z.infer<typeof question>;
export type RepoPart = z.infer<typeof repoPart>;
export type TaskCard = z.infer<typeof taskCard>;
export type UmbrellaCounts = z.infer<typeof umbrellaCounts>;
export type NeedsCategory = (typeof NEEDS_CATEGORIES)[number];
export type TriageLabel = (typeof TRIAGE_LABELS)[number];
export type ColumnId = z.infer<typeof column>;
export type Status = z.infer<typeof status>;

export type ActionId = (typeof ACTION_IDS)[number];
