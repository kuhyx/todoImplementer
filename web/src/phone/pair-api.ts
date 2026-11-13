/** POST /api/pair (PC only): mint a one-time pairing link for a phone. Shape: contracts/pair.schema.json. */
import { z } from "zod";

import { csrfToken } from "@/lib/boot";
import { ApiError, readJson, send, shapeMessage } from "@/lib/http";

const PAIR_URL = "/api/pair";

export const pairResponse = z.strictObject({ expires_at: z.int(), url: z.string() });
export type Pair = z.infer<typeof pairResponse>;

/** Same CSRF header as every other POST; the server refuses it unless the request is local. */
export async function mintPair(): Promise<Pair> {
  const csrf = csrfToken();
  if (csrf === null) throw new ApiError(`${PAIR_URL}: this page has no token`, { code: "no_token", status: 0 });
  const response = await send(PAIR_URL, { body: "{}", headers: { "Content-Type": "application/json", "X-Todoimpl-Token": csrf }, method: "POST" });
  if (!response.ok) throw new ApiError(`${PAIR_URL}: HTTP ${String(response.status)}`, { code: "http", status: response.status });
  const parsed = pairResponse.safeParse(await readJson(PAIR_URL, response));
  if (!parsed.success) throw new ApiError(shapeMessage(PAIR_URL, parsed.error), { code: "shape", status: response.status });
  return parsed.data;
}
