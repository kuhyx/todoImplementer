/** POST one ask click (same CSRF header as every POST); resolves with the command result, if any. */
import { ApiError, readJson, send, shapeMessage } from "@/lib/http";
import { type AskItem, askResponse, type AskVerb } from "@/lib/schemas-asks";

export async function postAsk(id: string, verb: AskVerb, body: Record<string, unknown>, csrf: string): Promise<AskItem["result"]> {
  const url = `/api/task/${encodeURIComponent(id)}/ask/${verb}`;
  const response = await send(url, {
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", "X-Todoimpl-Token": csrf },
    method: "POST",
  });
  const parsed = askResponse.safeParse(await readJson(url, response));
  if (!parsed.success) throw new ApiError(shapeMessage(url, parsed.error), { code: "shape", status: response.status });
  if (!parsed.data.ok) throw new ApiError(parsed.data.error.message, { code: parsed.data.error.code, status: response.status });
  return parsed.data.result;
}
