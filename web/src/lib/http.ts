/** Every request goes through here: status check, then Zod parse (R9 boundary). */
import type { z } from "zod";

import type { ActionId, TaskCard } from "@/lib/schemas-common";

import { bodyFor, type Payload, routes } from "@/lib/routes";
import { postResponse } from "@/lib/schemas";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, options: ErrorOptions & { code: string; status: number }) {
    super(message, options);
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
  }
}

export const errorText = (error: unknown): string => (Error.isError(error) ? error.message : "unknown error");

function shapeMessage(url: string, error: z.ZodError): string {
  const path = error.issues.slice(0, 1).flatMap((issue) => issue.path).join(".");
  return `${url}: the server sent an unexpected shape at ${path === "" ? "root" : path}`;
}

async function readJson(url: string, response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    throw new ApiError(`${url}: the server sent something that is not JSON`, { code: "not_json", status: response.status });
  }
}

async function send(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch {
    throw new ApiError(`${url}: cannot reach the server`, { code: "network", status: 0 });
  }
}

export async function getJson<S extends z.ZodType>(url: string, schema: S): Promise<z.infer<S>> {
  const response = await send(url, { cache: "no-store" });
  if (!response.ok) throw new ApiError(`${url}: HTTP ${String(response.status)}`, { code: "http", status: response.status });
  const parsed = schema.safeParse(await readJson(url, response));
  if (!parsed.success) throw new ApiError(shapeMessage(url, parsed.error), { code: "shape", status: response.status });
  return parsed.data;
}

/** POST one action. Resolves with the server's updated card; rejects with the server's own message. */
export async function postAction(id: string, action: ActionId, payload: Payload, csrf: string): Promise<TaskCard> {
  const url = routes.post(id, action);
  const response = await send(url, {
    body: JSON.stringify(bodyFor(action, payload)),
    headers: { "Content-Type": "application/json", "X-Todoimpl-Token": csrf },
    method: "POST",
  });
  const parsed = postResponse.safeParse(await readJson(url, response));
  if (!parsed.success) throw new ApiError(shapeMessage(url, parsed.error), { code: "shape", status: response.status });
  if (!parsed.data.ok) throw new ApiError(parsed.data.error.message, { code: parsed.data.error.code, status: response.status });
  return parsed.data.task;
}
