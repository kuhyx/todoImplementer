/** The page's one request: the task's raw issue log (GET /api/task/<id>/issues, ndjson), parsed line by line. */
import { type Issue, parseLog } from "@/issues/schemas";
import { ApiError, send } from "@/lib/http";
import { routes } from "@/lib/routes";

/** The task's issues in file order; null when the server knows no such task (404). */
export async function loadIssues(task: string): Promise<Issue[] | null> {
  const url = routes.issues(task);
  const response = await send(url, { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new ApiError(`${url}: HTTP ${String(response.status)}`, { code: "http", status: response.status });
  return parseLog(await response.text());
}
