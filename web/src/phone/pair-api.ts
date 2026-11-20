/** POST /api/pair's answer (contracts/pair.schema.json). The page has no QR button any more (kuhy, 2026-11-20); the route stays for the phone CLI. */
import { z } from "zod";

export const pairResponse = z.strictObject({ expires_at: z.int(), url: z.string() });
export type Pair = z.infer<typeof pairResponse>;
