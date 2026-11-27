/** POST /api/task/<card>/part-edit (856c0f0a): a part's new title and text. Resolves with the server's fresh card. */
import type { TaskCard } from "@/lib/schemas-common";

import { ApiError, readJson, send, shapeMessage } from "@/lib/http";
import { postResponse } from "@/lib/schemas";

export const partEditPath = (card: string): string => `/api/task/${encodeURIComponent(card)}/part-edit`;

export async function postPartEdit(card: string, part: string, title: string, body: string, csrf: string): Promise<TaskCard> {
  const url = partEditPath(card);
  const response = await send(url, {
    body: JSON.stringify({ body, part, title }),
    headers: { "Content-Type": "application/json", "X-Todoimpl-Token": csrf },
    method: "POST",
  });
  const parsed = postResponse.safeParse(await readJson(url, response));
  if (!parsed.success) throw new ApiError(shapeMessage(url, parsed.error), { code: "shape", status: response.status });
  if (!parsed.data.ok) throw new ApiError(parsed.data.error.message, { code: parsed.data.error.code, status: response.status });
  return parsed.data.task;
}
