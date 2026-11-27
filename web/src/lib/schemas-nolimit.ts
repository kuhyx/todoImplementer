/** Zod mirror of contracts/nolimit.schema.json: the tokenless runner's row inside GET /api/usage. */
import { z } from "zod";

import { epoch } from "@/lib/schemas-common";

export const nolimitResult = z.enum(["deployed", "pushed", "green", "red", "slow", "stopped", "readonly"]);

export const nolimit = z.strictObject({
  active: z.boolean(),
  at: epoch.nullable(),
  repo: z.string().nullable(),
  result: nolimitResult.nullable(),
});

export type NoLimit = z.infer<typeof nolimit>;
