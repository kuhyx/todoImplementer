/** The issue table: sortable icon headers, one row per log line, symptom and action wrapped in full. */
import type { Query } from "@/issues/model";
import type { Issue } from "@/issues/schemas";
import type { SortKey } from "@/usage/table-model";

import { icon } from "@/components/icons";
import { COLUMN_ICON, COLUMN_LABEL, label, STATE_ICON, STATE_LABEL, STATE_TONE } from "@/issues/labels";
import { ageLabel, isoStamp, SORT_KEYS, stampLabel } from "@/issues/model";
import { h } from "@/lib/dom";

export type SortName = (typeof SORT_KEYS)[number];
const ARROW = { ascending: "▲", descending: "▼", none: "" } as const;

export interface TableContext {
  items: readonly Issue[];
  nowMs: number;
  onSort: (key: SortName, isExtend: boolean) => void;
  query: Query;
}

function sortOrder(at: SortKey | undefined): keyof typeof ARROW {
  if (at === undefined) return "none";
  return at.desc ? "descending" : "ascending";
}

function sortHead(key: SortName, context: TableContext): HTMLTableCellElement {
  const order = sortOrder(context.query.sort.find((sort) => sort.key === key));
  const button = h(
    "button",
    {
      attrs: { "aria-label": COLUMN_LABEL[key], title: COLUMN_LABEL[key], type: "button" },
      class: "sort-btn",
      on: { click: (event) => { context.onSort(key, event.shiftKey); } },
    },
    icon(COLUMN_ICON[key]),
    h("span", { attrs: { "aria-hidden": "true" }, class: "arrow", text: ARROW[order] }),
  );
  return h("th", { attrs: { "aria-sort": order, "data-key": key, scope: "col" }, class: `col-${key}` }, button);
}

function stateMark(issue: Issue): HTMLElement {
  const name = STATE_LABEL[issue.state];
  return h("span", { attrs: { "aria-label": name, "data-tone": STATE_TONE[issue.state], role: "img", title: name }, class: "mark" }, icon(STATE_ICON[issue.state]));
}

/** A cell that names its column on narrow screens (the CSS turns rows into cards there and shows the icon). */
function cell(key: SortName, ...children: (HTMLElement | string)[]): HTMLTableCellElement {
  return h("td", { attrs: { "data-key": key }, class: `col-${key}` }, h("span", { attrs: { "aria-hidden": "true" }, class: "cell-icon" }, icon(COLUMN_ICON[key])), ...children);
}

/** The model name; a logged issue without one shows a muted dash, a raw row shows nothing. */
function modelPart(issue: Issue): HTMLElement {
  const isNamed = issue.model !== "" || issue.state === "raw";
  return isNamed ? h("code", { text: issue.model }) : h("span", { attrs: { "aria-label": label.noModel, title: label.noModel }, class: "none", text: "–" });
}

function row(issue: Issue, nowMs: number): HTMLTableRowElement {
  const isRaw = issue.state === "raw";
  return h(
    "tr",
    { attrs: { "data-line": issue.line, "data-state": issue.state } },
    h("td", { attrs: { "data-key": "ts", title: stampLabel(issue.ts) }, class: "col-ts num" }, h("time", { attrs: { datetime: isoStamp(issue.ts) }, text: ageLabel(issue.ts, nowMs) })),
    cell("child", h("span", { class: "repo", text: issue.child })),
    cell("phase", h("code", { text: issue.phase })),
    cell("model", modelPart(issue)),
    h("td", { attrs: { "data-key": "state" }, class: "col-state" }, stateMark(issue)),
    cell("symptom", isRaw ? h("code", { class: "raw-line", text: issue.raw }) : h("p", { class: "prose", text: issue.symptom })),
    cell("action", h("p", { class: "prose", text: issue.action })),
  );
}

export function renderTable(context: TableContext): HTMLElement {
  return h(
    "div",
    { class: "table-scroll" },
    h(
      "table",
      { attrs: { "aria-label": label.table } },
      h("thead", {}, h("tr", {}, ...SORT_KEYS.map((key) => sortHead(key, context)))),
      h("tbody", {}, ...context.items.map((issue) => row(issue, context.nowMs))),
    ),
  );
}
