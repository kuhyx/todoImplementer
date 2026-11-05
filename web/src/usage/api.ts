/** Every request: status check, then a Zod parse. A bad shape is an error, never an empty table. */
import type { z } from "zod";

import { withQuery } from "@/usage/route";
import { contextFileDetail, contextPanel, overviewPanel, sessionDetail, sessionsPanel, tokensIndex } from "@/usage/schemas";
import { abPanel, anomaliesPanel, efficiencyPanel, genericPanel, itemsPanel, leversPanel } from "@/usage/schemas-panels";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, options: ErrorOptions & { status: number }) {
    super(message, options);
    this.name = "ApiError";
    this.status = options.status;
  }
}

export const FILTER_KEYS = ["cwd", "from", "model", "scope", "to", "window"] as const;
const BASE = "/api/tokens";

export async function getJson<S extends z.ZodType>(url: string, schema: S, signal?: AbortSignal): Promise<z.infer<S>> {
  let response: Response;
  try {
    response = await fetch(url, { cache: "no-store", signal: signal ?? null });
  } catch (error) {
    if (signal?.aborted === true) throw error;
    throw new ApiError(`${url}: cannot reach the server`, { status: 0 });
  }
  if (!response.ok) throw new ApiError(`${url}: HTTP ${String(response.status)}`, { status: response.status });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(`${url}: the server sent something that is not JSON`, { status: response.status });
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    const where = parsed.error.issues.map((issue) => issue.path.join(".")).find(Boolean) ?? "root";
    throw new ApiError(`${url}: unexpected shape at ${where}`, { status: response.status });
  }
  return parsed.data;
}

/** The global filters of a hash, in the order the API documents them. */
export function filterQuery(parameters: URLSearchParams): URLSearchParams {
  const out = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    const value = parameters.get(key) ?? "";
    if (value !== "" && !(key === "scope" && value === "all")) out.set(key, value);
  }
  return out;
}

/** `tables` are asked for in full (limit 0): sort and filter run here, so a cut list would sort the wrong rows. */
function panelUrl(name: string, parameters: URLSearchParams, tables: readonly string[]): string {
  const query = filterQuery(parameters);
  for (const table of tables) query.set(`t.${table}.limit`, "0");
  const text = query.toString();
  return withQuery(`${BASE}/panel/${encodeURIComponent(name)}`, text);
}

export type Loader<T> = (parameters: URLSearchParams, signal?: AbortSignal) => Promise<T>;

function panel<S extends z.ZodType>(name: string, schema: S, tables: readonly string[]): Loader<z.infer<S>> {
  return (parameters, signal) => getJson(panelUrl(name, parameters, tables), schema, signal);
}

export const loadAb = panel("ab", abPanel, []);
export const loadAnomalies = panel("anomalies", anomaliesPanel, ["spikes", "expensive", "loops", "categories"]);
export const loadContext = panel("context", contextPanel, ["files"]);
export const loadEfficiency = panel("efficiency", efficiencyPanel, ["done", "commits", "estimate", "notes", "notes_weekly"]);
export const loadLevers = panel("levers", leversPanel, ["rows"]);
export const loadOverview = panel("overview", overviewPanel, ["daily", "weekly"]);
export const loadSessions = panel("sessions", sessionsPanel, ["sessions"]);

export const loadGeneric = (name: string): Loader<z.infer<typeof genericPanel>> => panel(name, genericPanel, []);
export const loadIndex = (signal?: AbortSignal): Promise<z.infer<typeof tokensIndex>> => getJson(BASE, tokensIndex, signal);

export function loadItems(parameters: URLSearchParams, signal?: AbortSignal): Promise<z.infer<typeof itemsPanel>> {
  return getJson(withQuery(`${BASE}/items`, filterQuery(parameters).toString()), itemsPanel, signal);
}

export function loadSession(key: string, signal?: AbortSignal): Promise<z.infer<typeof sessionDetail>> {
  return getJson(`${BASE}/session/${encodeURIComponent(key)}`, sessionDetail, signal);
}

export function loadFile(path: string, signal?: AbortSignal): Promise<z.infer<typeof contextFileDetail>> {
  return getJson(`${BASE}/context-file?path=${encodeURIComponent(path)}`, contextFileDetail, signal);
}
