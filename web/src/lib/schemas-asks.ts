/** contracts/ask.schema.json and the answers of POST /api/task/<id>/ask/<verb>. */
import { z } from "zod";

import { apiError } from "@/lib/schemas-common";

export const askItem = z.strictObject({
  answer: z.string().optional(),
  at: z.number().optional(),
  auto_at: z.number().optional(),
  command: z.string().optional(),
  id: z.string().regex(/^[a-z][a-z0-9_]{0,15}$/),
  mode: z.enum(["run", "add_run", "terminal"]).optional(),
  options: z.array(z.string().min(1)).min(2).max(8).optional(),
  recommended: z.string().optional(),
  result: z.strictObject({ capped: z.boolean(), exit: z.number().int(), tail: z.string() }).optional(),
  risk: z.enum(["reversible", "risky"]),
  shot: z.string().regex(/\.png$/).optional(),
  state: z.enum(["open", "answered", "auto", "done", "approved", "rejected"]),
  title: z.string().min(1),
  type: z.enum(["choice", "command", "screenshot"]),
  warning: z.boolean().optional(),
});
export type AskItem = z.infer<typeof askItem>;

export const askResponse = z.union([
  z.strictObject({ ok: z.literal(true), result: askItem.shape.result.optional() }),
  z.strictObject({ error: apiError, ok: z.literal(false) }),
]);

export type AskVerb = "answer" | "approve" | "reject" | "run" | "take-recommended" | "undo";
