/** Network edge of the merge suggestions: GET the list, POST a merge or dismiss click (same CSRF header as all POSTs). */
import { ApiError, getJson, readJson, send, shapeMessage } from "@/lib/http";
import { routes } from "@/lib/routes";
import { type MergeActionId, mergeResponse, type Suggestion, suggestions } from "@/lib/schemas-merge";

export async function getMerges(): Promise<Suggestion[]> {
  const body = await getJson(routes.merges, suggestions);
  return body.suggestions;
}

/** Resolves with the fresh suggestions; rejects with the server's own message. */
export async function postMerge(group: string, action: MergeActionId, csrf: string): Promise<Suggestion[]> {
  const url = routes.mergeAction(group, action);
  const response = await send(url, {
    body: "{}",
    headers: { "Content-Type": "application/json", "X-Todoimpl-Token": csrf },
    method: "POST",
  });
  const parsed = mergeResponse.safeParse(await readJson(url, response));
  if (!parsed.success) throw new ApiError(shapeMessage(url, parsed.error), { code: "shape", status: response.status });
  if (!parsed.data.ok) throw new ApiError(parsed.data.error.message, { code: parsed.data.error.code, status: response.status });
  return parsed.data.suggestions;
}
