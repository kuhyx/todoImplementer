/** Zod mirrors of the GET/POST/SSE contracts (board, task, usage, version, live, response). */
import { z } from "zod";

import { autonomy } from "@/lib/schemas-autonomy";
import {
  actions, apiError, checks, column, epoch, itemId, lesson, limit, liveCheck, needs, question, selfCheck, stage, status,
  taskCard, usd,
} from "@/lib/schemas-common";

const keyState = z.enum(["ok", "expiring", "expired", "invalid", "missing", "check_failed"]);

export const board = z.strictObject({
  api_key: z
    .strictObject({
      expires: z.iso.date().nullable(),
      level: z.enum(["ok", "warn", "error"]),
      state: keyState,
      text: z.string().min(1),
    })
    .optional(),
  build: z.string().min(1),
  columns: z
    .array(z.strictObject({ count: z.number().int().min(0), id: column, label: z.string().min(1) }))
    .length(5),
  error: apiError.nullable().optional(),
  generated_at: epoch,
  limit,
  repos: z.array(z.string().min(1)),
  slots: z.strictObject({ used: z.number().int().min(0) }),
  tasks: z.array(taskCard),
});

export const taskDetail = z.strictObject({
  asks: z.array(question),
  body: z.string(),
  branch: z.string().nullable(),
  card: taskCard,
  checks: checks.nullable(),
  diff: z
    .strictObject({
      files: z.array(
        z.strictObject({ added: z.number().int().min(0), path: z.string(), removed: z.number().int().min(0) }),
      ),
      patch: z.string(),
      truncated: z.boolean(),
    })
    .nullable(),
  done_check: z.string().nullable(),
  error: z.string().nullable(),
  lesson: lesson.nullable(),
  live_check: liveCheck.nullable(),
  plan_md: z.string().nullable(),
  questions: z.array(question),
  resume_command: z.string().nullable(),
  self_check: selfCheck,
  skills_loaded: z.array(z.string()),
  stages: z.array(z.strictObject({ ended: epoch.nullable(), stage, started: epoch })),
  worktree: z.string().nullable(),
});

const usageWindow = z
  .strictObject({ resets_at: epoch, status: z.string(), utilization: z.number().min(0) })
  .nullable();

export const usage = z.strictObject({
  autonomy,
  cost: z.strictObject({
    per_task: z.array(z.strictObject({ cost_usd: usd, id: itemId, title: z.string() })),
    today_usd: usd,
    total_usd: usd,
  }),
  five_hour: usageWindow,
  generated_at: epoch,
  limit,
  overage: z.strictObject({ status: z.string(), using: z.boolean() }),
  seven_day: usageWindow,
});

export const version = z.strictObject({ build: z.string().min(1), version: z.string().min(1) });

export const postResponse = z.union([
  z.strictObject({ ok: z.literal(true), task: taskCard }),
  z.strictObject({ error: apiError, ok: z.literal(false) }),
]);

export const liveEvent = z.discriminatedUnion("type", [
  z.strictObject({
    at: epoch,
    kind: z.enum(["text", "tool", "result", "error", "system", "user"]),
    seq: z.number().int().min(1),
    text: z.string(),
    tool: z.string().nullable(),
    type: z.literal("activity"),
  }),
  z.strictObject({
    actions,
    column,
    current: z.string(),
    needs,
    stage: stage.nullable(),
    status,
    type: z.literal("stage"),
  }),
  z.strictObject({ cost_usd: usd, type: z.literal("cost") }),
  z.strictObject({ status, type: z.literal("done") }),
]);

export type Board = z.infer<typeof board>;
export type TaskDetail = z.infer<typeof taskDetail>;
export type Usage = z.infer<typeof usage>;
export type LiveEvent = z.infer<typeof liveEvent>;
export type ActivityEvent = Extract<LiveEvent, { type: "activity" }>;
