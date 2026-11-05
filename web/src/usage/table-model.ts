/** Pure table logic: search, column filters, multi-key sort and the state's URL grammar (`t.<id>.q|sort|limit|f.<col>`, as the old API). */
import { fuzzyMatch } from "@kuhyx/web-ui";

import { cellText } from "@/usage/format";

export type Kind = "enum" | "number" | "text";
export type Row = Record<string, unknown>;

export interface Column<R extends Row = Row> {
  href?: (row: R) => string;
  key: string;
  kind: Kind;
  label: string;
  /** Display text only; the raw value still drives sort and filter. */
  show?: (value: unknown, row: R) => string;
}

export interface SortKey {
  desc: boolean;
  key: string;
}

export interface TableState {
  filters: Record<string, string>;
  limit: null | number;
  q: string;
  sort: SortKey[];
}

export const EMPTY_TABLE: TableState = { filters: {}, limit: null, q: "", sort: [] };
export const PAGE = 200;

export function shown<R extends Row>(column: Column<R>, row: R): string {
  const value = row[column.key];
  return column.show === undefined ? cellText(value) : column.show(value, row);
}

export function readTable(parameters: URLSearchParams, id: string): TableState {
  const prefix = `t.${id}.`;
  const filters: Record<string, string> = {};
  for (const [key, value] of parameters) {
    if (value !== "" && key.startsWith(`${prefix}f.`)) filters[key.slice(prefix.length + 2)] = value;
  }
  const sort = (parameters.get(`${prefix}sort`) ?? "")
    .split(",")
    .filter((part) => part.replace(/^-/v, "") !== "")
    .map((part) => ({ desc: part.startsWith("-"), key: part.replace(/^-/v, "") }));
  const limit = parameters.get(`${prefix}limit`) ?? "";
  return { filters, limit: /^\d+$/v.test(limit) ? Number(limit) : null, q: parameters.get(`${prefix}q`) ?? "", sort };
}

/** Replace this table's keys in `params`; every other table and filter stays. */
export function writeTable(parameters: URLSearchParams, id: string, state: TableState): URLSearchParams {
  const prefix = `t.${id}.`;
  const next = new URLSearchParams([...parameters].filter(([key]) => !key.startsWith(prefix)));
  const put = (key: string, value: string): void => {
    if (value !== "") next.set(`${prefix}${key}`, value);
  };
  put("q", state.q);
  put("sort", state.sort.map((s) => `${s.desc ? "-" : ""}${s.key}`).join(","));
  put("limit", state.limit === null ? "" : String(state.limit));
  for (const [column, rule] of Object.entries(state.filters)) put(`f.${column}`, rule);
  return next;
}

function compare(a: unknown, b: unknown): number {
  return typeof a === "number" && typeof b === "number" ? a - b : cellText(a).localeCompare(cellText(b), "en", { numeric: true });
}

function matchesRule(rule: string, value: unknown): boolean {
  if (rule.startsWith("=")) return rule.slice(1).split("|").includes(cellText(value));
  if (rule.includes("..")) {
    const [lo = "", hi = ""] = rule.split("..", 2);
    return typeof value === "number" && (lo === "" || value >= Number(lo)) && (hi === "" || value <= Number(hi));
  }
  return fuzzyMatch(rule.replace(/^~/v, ""), cellText(value));
}

const isMissing = (value: unknown): boolean => value === null || value === undefined;

function sorted<R extends Row>(rows: R[], keys: SortKey[]): R[] {
  if (keys.length === 0) return rows;
  return rows.toSorted((a, b) => {
    for (const { desc, key } of keys) {
      const left = a[key];
      const right = b[key];
      if (isMissing(left) || isMissing(right)) {
        if (isMissing(left) !== isMissing(right)) return isMissing(left) ? 1 : -1;
        continue;
      }
      const order = compare(left, right);
      if (order !== 0) return desc ? -order : order;
    }
    return 0;
  });
}

/** Rows that survive search and filters, in sort order. */
export function applyTable<R extends Row>(rows: R[], columns: Column<R>[], state: TableState): R[] {
  const words = state.q.split(/\s+/v).filter((word) => word !== "");
  const kept = rows.filter(
    (row) => {
      return words.every((word) => columns.some((column) => fuzzyMatch(word, shown(column, row)))) &&
      Object.entries(state.filters).every(([key, rule]) => matchesRule(rule, row[key]));
    },
  );
  return sorted(kept, state.sort);
}

export function distinct(rows: Row[], key: string): string[] {
  return [...new Set(rows.map((row) => cellText(row[key])))].toSorted((a, b) => a.localeCompare(b));
}

/** Header click: none, ascending, descending, none. Shift keeps the other keys. */
export function cycleSort(current: SortKey[], key: string, shouldExtend: boolean): SortKey[] {
  const at = current.find((s) => s.key === key);
  const rest = shouldExtend ? current.filter((s) => s.key !== key) : [];
  if (at === undefined) return [...rest, { desc: false, key }];
  return at.desc ? rest : [...rest, { desc: true, key }];
}
