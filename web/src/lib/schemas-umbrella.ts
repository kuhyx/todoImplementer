/** Zod mirrors of contracts/common.schema.json umbrella_row and umbrella_detail (drawer of an umbrella note). */
import { z } from "zod";

import { itemId, stage, status, usd } from "@/lib/schemas-common";

export const VERDICTS = ["clean", "coached", "fixed", "escalate"] as const;

export const umbrellaRow = z.strictObject({
  cost_usd: usd,
  error: z.string().nullable(),
  free: z.boolean().nullable(),
  id: itemId,
  issues: z.number().int().min(0),
  repo: z.string(),
  round: z.number().int().nullable(),
  stage: stage.nullable(),
  status,
  title: z.string(),
  verdict: z.enum(VERDICTS).nullable(),
});

const umbrellaRound = z.strictObject({
  children: z.array(
    z.strictObject({
      checks: z.boolean().nullable(),
      detail: z.string(),
      free: z.boolean(),
      id: z.string(),
      ok: z.boolean(),
      verdict: z.enum(VERDICTS),
    }),
  ),
  n: z.number().int().min(1),
  next: z.number().int().min(1),
  width: z.number().int().min(1),
});

export const umbrellaDetail = z.strictObject({
  round: z.number().int().min(0),
  rounds: z.array(umbrellaRound),
  rows: z.array(umbrellaRow),
  width: z.number().int().min(1),
});

export type UmbrellaDetail = z.infer<typeof umbrellaDetail>;
export type UmbrellaRow = z.infer<typeof umbrellaRow>;
