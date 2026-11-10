/** Zod mirror of contracts/merge.schema.json: the suggestions and the answer to a merge or dismiss click. */
import { z } from "zod";

import { itemId } from "@/lib/schemas-common";

export const MERGE_ACTIONS = ["merge", "dismiss"] as const;
export type MergeActionId = (typeof MERGE_ACTIONS)[number];

const groupId = z.string().regex(/^[0-9a-f]{12}$/);

const member = z.strictObject({ id: itemId, repo: z.string().min(1), title: z.string().min(1) });

const mergeAction = z
  .strictObject({
    enabled: z.boolean(),
    id: z.enum(MERGE_ACTIONS),
    label: z.string().min(1),
    reason: z.string().nullable(),
  })
  .refine((a) => a.enabled || (a.reason !== null && a.reason.length > 0), { message: "a disabled action needs a reason" });

export const suggestion = z.strictObject({
  actions: z.array(mergeAction).length(2),
  id: groupId,
  members: z.array(member).min(2),
  reason: z.string().min(1),
  title: z.string().min(1),
});

export const suggestions = z.strictObject({ suggestions: z.array(suggestion) });

const errorCode = z.enum(["bad_request", "forbidden", "not_found", "disabled", "conflict", "internal", "upstream_unavailable"]);

export const mergeResponse = z.union([
  z.strictObject({ new_id: z.string().min(1).nullable(), ok: z.literal(true), suggestions: z.array(suggestion) }),
  z.strictObject({ error: z.strictObject({ code: errorCode, message: z.string().min(1) }), ok: z.literal(false) }),
]);

export type Suggestion = z.infer<typeof suggestion>;
export type Suggestions = z.infer<typeof suggestions>;
export type MergeAction = Suggestion["actions"][number];
