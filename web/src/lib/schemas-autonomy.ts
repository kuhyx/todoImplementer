/** Zod mirror of contracts/autonomy.schema.json (the `autonomy` block of GET /api/usage). */
import { z } from "zod";

const week = z.string().regex(/^\d{4}-W\d{2}$/v);
const direction = z.enum(["up", "down"]);
const count = z.number().int().min(0);
const percent = z.number().min(0).max(100);

export const countMetric = z.strictObject({
  direction,
  target: z.number(),
  value: count,
  weekly: z.array(z.strictObject({ value: count, week })),
});

export const rateMetric = z.strictObject({
  count,
  direction,
  finished: count,
  target: z.number(),
  value: percent.nullable(),
  weekly: z.array(z.strictObject({ count, finished: z.number().int().min(1), value: percent, week })),
});

export const autonomy = z.strictObject({
  backfilled: count,
  cards: count,
  criteria_failed: countMetric,
  done_unassisted: rateMetric,
  permission_asks: countMetric,
  questions_asked: countMetric,
});

export type Autonomy = z.infer<typeof autonomy>;
