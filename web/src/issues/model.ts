/** Pure page logic: the hash grammar (task + filters + table state), newest-first order, filters, counts and time labels. */
import type { Issue, IssueState } from "@/issues/schemas";

import { applyTable, type Column, readTable, type SortKey, writeTable } from "@/usage/table-model";

export type StateFilter = "all" | IssueState;

export interface Query {
  model: string;
  phase: string;
  q: string;
  repo: string;
  sort: SortKey[];
  state: StateFilter;
  task: string;
}

export const STATE_FILTERS: readonly StateFilter[] = ["all", "open", "fixed", "raw"];
export const EMPTY_QUERY: Query = { model: "", phase: "", q: "", repo: "", sort: [], state: "all", task: "" };
export const TABLE_ID = "i";
/** Sortable columns, in table order: the key each header sorts on. */
export const SORT_KEYS = ["ts", "child", "phase", "model", "state", "symptom", "action"] as const;
const FILTER_KEYS = ["model", "phase", "repo"] as const;

/** What the search box looks at: every text the row shows. */
const SEARCH: Column<Issue & Record<string, unknown>>[] = ["child", "phase", "model", "state", "symptom", "action"].map((key) => ({ key, kind: "text", label: key }));

export function readQuery(hash: string): Query {
  const parameters = new URLSearchParams(hash.replace(/^#/v, ""));
  const table = readTable(parameters, TABLE_ID);
  const pick = (key: string): string => parameters.get(key) ?? "";
  return {
    model: pick("model"),
    phase: pick("phase"),
    q: table.q,
    repo: pick("repo"),
    sort: table.sort.filter((key) => (SORT_KEYS as readonly string[]).includes(key.key)),
    state: STATE_FILTERS.find((state) => state === parameters.get("state")) ?? "all",
    task: pick("task"),
  };
}

/** The hash for a query: the task first, defaults omitted. */
export function writeQuery(query: Query): string {
  const parameters = new URLSearchParams();
  if (query.task !== "") parameters.set("task", query.task);
  if (query.state !== "all") parameters.set("state", query.state);
  for (const key of FILTER_KEYS) if (query[key] !== "") parameters.set(key, query[key]);
  const text = writeTable(parameters, TABLE_ID, { filters: {}, limit: null, q: query.q, sort: query.sort }).toString();
  return text === "" ? "" : `#${text}`;
}

/** Newest first; a raw row (no time) goes by its place in the file, later lines first. */
export function newestFirst(issues: readonly Issue[]): Issue[] {
  return issues.toSorted((a, b) => (b.ts ?? -Infinity) - (a.ts ?? -Infinity) || b.line - a.line);
}

function isShown(issue: Issue, query: Query): boolean {
  return (
    (query.state === "all" || issue.state === query.state) &&
    (query.phase === "" || issue.phase === query.phase) &&
    (query.model === "" || issue.model === query.model) &&
    (query.repo === "" || issue.child === query.repo)
  );
}

/** The rows to show: filters, fuzzy search, then the header sort over the newest-first order. */
export function visibleIssues(issues: readonly Issue[], query: Query): Issue[] {
  const kept = newestFirst(issues).filter((issue) => isShown(issue, query)) as (Issue & Record<string, unknown>)[];
  return applyTable(kept, SEARCH, { filters: {}, limit: null, q: query.q, sort: query.sort });
}

export type Tally = [value: string, count: number][];

/** How often each value of `key` occurs, most frequent first; empty values (raw rows, no model) are left out. */
export function tally(issues: readonly Issue[], key: "child" | "model" | "phase"): Tally {
  const counts = new Map<string, number>();
  for (const issue of issues) if (issue[key] !== "") counts.set(issue[key], (counts.get(issue[key]) ?? 0) + 1);
  return [...counts].toSorted((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

export function stateCounts(issues: readonly Issue[]): Record<StateFilter, number> {
  const counts: Record<StateFilter, number> = { all: issues.length, fixed: 0, open: 0, raw: 0 };
  for (const issue of issues) counts[issue.state] += 1;
  return counts;
}

/** Compact time since the issue: 40s, 5m, 3h, 12d; "" for a raw row. */
export function ageLabel(ts: null | number, nowMs: number): string {
  if (ts === null) return "";
  const seconds = Math.max(0, Math.floor(nowMs / 1000 - ts));
  if (seconds < 60) return `${String(seconds)}s`;
  if (seconds < 3600) return `${String(Math.floor(seconds / 60))}m`;
  return seconds < 86_400 ? `${String(Math.floor(seconds / 3600))}h` : `${String(Math.floor(seconds / 86_400))}d`;
}

/** The absolute local time of an issue, for the cell's title. */
export function stampLabel(ts: null | number): string {
  if (ts === null) return "";
  const date = new Date(ts * 1000);
  return date.toLocaleString();
}

/** The machine-readable time of an issue, for `<time datetime>`; null for a raw row. */
export function isoStamp(ts: null | number): null | string {
  if (ts === null) return null;
  const date = new Date(ts * 1000);
  return date.toISOString();
}
