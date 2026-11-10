/** Zod mirror of contracts/free.schema.json: the free-model gateway's cached reading inside GET /api/usage. */
import { z } from "zod";

import { epoch } from "@/lib/schemas-common";

const percent = z.number().min(0).max(100).nullable();
const count = z.number().int().min(0);

export const providerState = z.enum(["ok", "cooling", "failing", "off"]);
export const stepState = z.enum(["ok", "cooling", "failing"]);
export const gatewayState = z.enum(["ok", "stale", "down", "unknown"]);

export const free = z.strictObject({
  at: epoch.nullable(),
  combo: z
    .strictObject({
      fallback_pct: percent,
      name: z.string(),
      ok_pct: percent,
      requests: count,
      steps: z.array(
        z.strictObject({ last: epoch.nullable(), model: z.string(), ok_pct: percent, provider: z.string(), requests: count, state: stepState }),
      ),
    })
    .nullable(),
  counts: z.strictObject({ cooling: count, failing: count, ok: count, providers: count, quota_known: count }),
  error: z.string().nullable(),
  models: z.strictObject({ cooling: count, total: count }),
  providers: z.array(z.strictObject({ failures: count, id: z.string(), quota: z.boolean(), state: providerState, until: epoch.nullable() })),
  quotas: z.array(
    z.strictObject({
      label: z.string(),
      left_pct: z.number().min(0).max(100),
      provider: z.string(),
      reset_at: epoch.nullable(),
      total: z.number().gt(0),
      used: z.number().min(0),
    }),
  ),
  state: gatewayState,
  tokens: z.strictObject({ in: count, ours: count.nullable(), out: count, requests: count }).nullable(),
});

export type Free = z.infer<typeof free>;
