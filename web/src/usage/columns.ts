import type { Column, Row } from "@/usage/table-model";

import { compact, duration, share, stamp, usd } from "@/usage/format";

type Extra = Partial<Pick<Column, "href" | "show">>;
type Number_ = null | number;

const make = (kind: Column["kind"], key: string, label: string, extra: Extra = {}): Column => ({ key, kind, label, ...extra });
const view = (format: (value: Number_) => string) => (key: string, label: string): Column => make("number", key, label, { show: (value) => format(value as Number_) });

/** Column builders: the key says where the value lives, the builder says how to read and show it. */
export const col = {
  big: view(compact),
  count: (key: string, label: string): Column => make("number", key, label),
  link: (key: string, label: string, href: (row: Row) => string): Column => make("text", key, label, { href }),
  money: view(usd),
  pct: view(share),
  secs: view(duration),
  tag: (key: string, label: string): Column => make("enum", key, label),
  text: (key: string, label: string, show?: Column["show"]): Column => make("text", key, label, show === undefined ? {} : { show }),
  when: view(stamp),
};

const ENUM_MAX = 12;

/** Columns for rows nobody wrote a schema for: the first row's keys, formatted by name (cost, share, seconds, tokens). */
export function inferColumns(rows: readonly Row[]): Column[] {
  const first = rows[0] ?? {};
  return Object.entries(first).map(([key, sample]) => {
    const label = key.replaceAll("_", " ");
    if (typeof sample !== "number") {
      const kinds = new Set(rows.map((row) => JSON.stringify(row[key])));
      return typeof sample === "string" && kinds.size > 1 && kinds.size <= ENUM_MAX ? col.tag(key, label) : col.text(key, label);
    }
    if (/usd|cost/v.test(key)) return col.money(key, label);
    if (/share|rate/v.test(key)) return col.pct(key, label);
    if (key.endsWith('_s')) return col.secs(key, label);
    return /tokens|bytes/v.test(key) ? col.big(key, label) : col.count(key, label);
  });
}
