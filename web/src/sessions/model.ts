/** Pure page logic: the hash grammar, the done/filter rules, search and sort (via the usage table model), grouping and the age figure. */
import type { Mark, Session, Status } from "@/sessions/schemas";

import { MARKS, STATUSES } from "@/sessions/schemas";
import { applyTable, type Column, readTable, type SortKey, writeTable } from "@/usage/table-model";

export type MarkFilter = "all" | Mark;
export type Item = Session & { age: null | number; markRank: number };

export interface Query {
  mark: MarkFilter;
  /** Only sessions idle for more than this many days; null = off. */
  older: null | number;
  project: string;
  q: string;
  showDone: boolean;
  sort: SortKey[];
  statuses: Status[];
}

export const EMPTY_QUERY: Query = { mark: "all", older: null, project: "", q: "", showDone: false, sort: [], statuses: [] };
export const TABLE_ID = "s";
/** Sortable columns: the sort key each header sorts on. */
export const SORT_KEYS = ["group", "age", "project", "title", "markRank"] as const;
export const MAX_RESUME = 5;
export const DAY_MS = 86_400_000;
const MARK_RANK: Record<Mark, number> = { manual: 0, open: 2, tag: 1 };
const DONE_STATUSES: ReadonlySet<Status> = new Set(["continuing", "done"]);

/** What the search box looks at: project, title, cwd, id and the status words. */
const SEARCH: Column<Item>[] = [
  { key: "project", kind: "text", label: "project" },
  { key: "title", kind: "text", label: "title" },
  { key: "cwd", kind: "text", label: "cwd" },
  { key: "id", kind: "text", label: "id" },
  { key: "status", kind: "text", label: "status", show: (value) => String(value).replace("_", " ") },
];

export function toItem(session: Session): Item {
  const stamp = session.last_ts === null ? NaN : Date.parse(session.last_ts);
  // Ascending age = youngest first, so the first click on the age header shows what moved last.
  return { ...session, age: Number.isNaN(stamp) ? null : -stamp, markRank: MARK_RANK[session.mark] };
}

export function readQuery(hash: string): Query {
  const parameters = new URLSearchParams(hash.replace(/^#/v, ""));
  const table = readTable(parameters, TABLE_ID);
  const older = Number(parameters.get("older") ?? "");
  const listed = new Set((parameters.get("status") ?? "").split(","));
  return {
    mark: MARKS.find((mark) => mark === parameters.get("mark")) ?? "all",
    older: Number.isFinite(older) && parameters.has("older") && older > 0 ? older : null,
    project: parameters.get("project") ?? "",
    q: table.q,
    showDone: parameters.get("done") === "1",
    sort: table.sort.filter((key) => (SORT_KEYS as readonly string[]).includes(key.key)),
    statuses: STATUSES.filter((status) => listed.has(status)),
  };
}

/** The hash for a query; defaults are omitted, so the empty query is the empty hash. */
export function writeQuery(query: Query): string {
  const parameters = writeTable(new URLSearchParams(), TABLE_ID, { filters: {}, limit: null, q: query.q, sort: query.sort });
  if (query.showDone) parameters.set("done", "1");
  if (query.statuses.length > 0) parameters.set("status", query.statuses.join(","));
  if (query.project !== "") parameters.set("project", query.project);
  if (query.older !== null) parameters.set("older", String(query.older));
  if (query.mark !== "all") parameters.set("mark", query.mark);
  const text = parameters.toString();
  return text === "" ? "" : `#${text}`;
}

/**
 * Done rows show when "show done" is on, when the mark filter asks for done rows, or when their own done/continuing status
 * is ticked; every other filter then applies on top.
 */
function isDoneAllowed(item: Item, query: Query): boolean {
  const isOwnStatus = DONE_STATUSES.has(item.status) && query.statuses.includes(item.status);
  return !item.done || query.showDone || query.mark === "manual" || query.mark === "tag" || isOwnStatus;
}

function isShown(item: Item, query: Query, nowMs: number): boolean {
  const idle = item.age === null ? null : nowMs + item.age;
  return (
    isDoneAllowed(item, query) &&
    (query.statuses.length === 0 || query.statuses.includes(item.status)) &&
    (query.project === "" || item.project === query.project) &&
    (query.mark === "all" || item.mark === query.mark) &&
    (query.older === null || (idle !== null && idle > query.older * DAY_MS))
  );
}

/** The rows to show: filters, then fuzzy search, then the sort; with no sort the server's grouped order stands. */
export function visibleItems(sessions: readonly Session[], query: Query, nowMs: number): Item[] {
  const kept = sessions.map((session) => toItem(session)).filter((item) => isShown(item, query, nowMs));
  return applyTable(kept, SEARCH, { filters: {}, limit: null, q: query.q, sort: query.sort });
}

export function statusCounts(sessions: readonly Session[]): Record<Status, number> {
  const counts = Object.fromEntries(STATUSES.map((status) => [status, 0])) as Record<Status, number>;
  for (const session of sessions) counts[session.status] += 1;
  return counts;
}

export function projectsOf(sessions: readonly Session[], keep: string): string[] {
  const names = new Set(sessions.map((session) => session.project));
  if (keep !== "") names.add(keep);
  return [...names].toSorted((a, b) => a.localeCompare(b));
}

/** The server's urgency groups of a list already in server order: one run per group, empty groups left out. */
export function groupRuns(items: readonly Item[]): { group: Item["group"]; items: Item[] }[] {
  const runs: { group: Item["group"]; items: Item[] }[] = [];
  for (const item of items) {
    const last = runs.at(-1);
    if (last?.group === item.group) last.items.push(item);
    else runs.push({ group: item.group, items: [item] });
  }
  return runs;
}

/** Ids a bulk action covers: selected rows that are still listed, in list order. */
export function selectedIds(selected: ReadonlySet<string>, items: readonly Item[]): string[] {
  return items.filter((item) => selected.has(item.id)).map((item) => item.id);
}

/** Compact idle time: 5m, 3h, 12d; "" when the transcript carried no time. */
export function ageLabel(item: Item, nowMs: number): string {
  if (item.age === null) return "";
  const minutes = Math.max(0, Math.floor((nowMs + item.age) / 60_000));
  if (minutes < 60) return `${String(minutes)}m`;
  return minutes < 1440 ? `${String(Math.floor(minutes / 60))}h` : `${String(Math.floor(minutes / 1440))}d`;
}
