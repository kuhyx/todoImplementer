/** Every request of the page: status check, then a Zod parse. A bad shape is an error, never an empty table. */
import { z } from "zod";

import { ApiError, getJson, readJson, send, shapeMessage } from "@/lib/http";
import { apiError } from "@/lib/schemas-common";
import { type MutationResult, mutationResult, type SessionList, sessionList } from "@/sessions/schemas";

export type Action = "delete" | "handoff" | "mark" | "resume";
export const LIST_URL = "/api/sessions";
export const actionUrl = (action: Action): string => `${LIST_URL}/${action}`;

const failure = z.strictObject({ error: apiError, ok: z.literal(false) });

export const loadSessions = (): Promise<SessionList> => getJson(LIST_URL, sessionList);

/** POST one mutation with the page's CSRF token. A guard refusal still resolves (HTTP 200, `refused`); only transport and 4xx reject. */
export async function postSessions(action: Action, body: Record<string, unknown>, csrf: string): Promise<MutationResult> {
  const url = actionUrl(action);
  const response = await send(url, {
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-Todoimpl-Token": csrf },
    method: "POST",
  });
  const payload = await readJson(url, response);
  if (!response.ok) {
    const refused = failure.safeParse(payload);
    const message = refused.success ? refused.data.error.message : `${url}: HTTP ${String(response.status)}`;
    throw new ApiError(message, { code: refused.success ? refused.data.error.code : "http", status: response.status });
  }
  const parsed = mutationResult.safeParse(payload);
  if (!parsed.success) throw new ApiError(shapeMessage(url, parsed.error), { code: "shape", status: response.status });
  return parsed.data;
}
