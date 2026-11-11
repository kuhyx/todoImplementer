/** The table: sortable icon headers, urgency group rows (while unsorted), selectable rows that expand to their details. */
import type { Item, Query } from "@/sessions/model";
import type { Outcome } from "@/sessions/parts";
import type { SortKey } from "@/usage/table-model";

import { icon } from "@/components/icons";
import { h } from "@/lib/dom";
import { renderMarkdown } from "@/lib/markdown";
import { type Perform, rowActions } from "@/sessions/actions";
import { COLUMN_ICON, COLUMN_LABEL, label, STATUS_LABEL } from "@/sessions/labels";
import { ageLabel, groupRuns, SORT_KEYS } from "@/sessions/model";
import { markGlyph, statusPill } from "@/sessions/parts";

export type SortName = (typeof SORT_KEYS)[number];
export const COLUMN_COUNT = 7;
const GROUP_STATUS = ["needs_action", "question", "untagged", "running", "done"] as const;
type Group = Item["group"];
const ARROW = { ascending: "▲", descending: "▼", none: "" } as const;

export interface TableContext {
  isBusy: boolean;
  items: Item[];
  nowMs: number;
  onSelect: (id: string, isRange: boolean) => void;
  onSelectAll: () => void;
  onSort: (key: SortName, isExtend: boolean) => void;
  onToggle: (id: string) => void;
  open: ReadonlySet<string>;
  outcomes: ReadonlyMap<string, Outcome>;
  perform: Perform;
  query: Query;
  selected: ReadonlySet<string>;
}

function sortOrder(at: SortKey | undefined): keyof typeof ARROW {
  if (at === undefined) return "none";
  return at.desc ? "descending" : "ascending";
}

function sortHead(key: SortName, context: TableContext): HTMLTableCellElement {
  const at = context.query.sort.find((sort) => sort.key === key);
  const order = sortOrder(at);
  const button = h("button", {
    attrs: { "aria-label": COLUMN_LABEL[key], title: COLUMN_LABEL[key], type: "button" },
    class: "sort-btn",
    on: { click: (event) => { context.onSort(key, event.shiftKey); } },
  });
  button.append(icon(COLUMN_ICON[key]), h("span", { attrs: { "aria-hidden": "true" }, class: "arrow", text: ARROW[order] }));
  return h("th", { attrs: { "aria-sort": order, "data-key": key, scope: "col" }, class: `col-${key}` }, button);
}

function head(context: TableContext): HTMLElement {
  const isAll = context.items.length > 0 && context.items.every((item) => context.selected.has(item.id));
  const box = h("input", { attrs: { "aria-label": label.selectAll, type: "checkbox" }, on: { change: context.onSelectAll } });
  box.checked = isAll;
  return h(
    "thead",
    {},
    h(
      "tr",
      {},
      h("th", { attrs: { scope: "col" }, class: "select-cell" }, box),
      ...SORT_KEYS.map((key) => sortHead(key, context)),
      h("th", { attrs: { scope: "col" }, class: "col-actions" }),
    ),
  );
}

function details(item: Item): HTMLElement {
  const line = (glyph: "folder" | "link" | "log" | "person", body: HTMLElement): HTMLElement =>
    h("div", { class: "detail-line" }, icon(glyph), body);
  return h(
    "td",
    { attrs: { colspan: COLUMN_COUNT }, class: "detail" },
    line("folder", h("code", { text: item.cwd })),
    line("link", h("code", { text: item.id })),
    line("person", h("p", { class: "prompt", text: item.last_user })),
    line("log", renderMarkdown(item.last_assistant)),
  );
}

function row(item: Item, context: TableContext): HTMLTableRowElement[] {
  const isOpen = context.open.has(item.id);
  const box = h("input", {
    attrs: { "aria-label": `${label.select} ${item.id}`, type: "checkbox" },
    on: { click: (event) => { context.onSelect(item.id, event.shiftKey); } },
  });
  box.checked = context.selected.has(item.id);
  const title = h("button", { attrs: { "aria-expanded": isOpen, "aria-label": item.title === "" ? item.id : item.title, type: "button" }, class: "title-btn", text: item.title === "" ? item.id.slice(0, 8) : item.title });
  const main = h(
    "tr",
    { attrs: { "data-id": item.id, "data-status": item.status }, class: item.done ? "dim" : "", on: { click: (event) => {
      if ((event.target as Element).closest("input, .row-actions") === null) context.onToggle(item.id);
    } } },
    h("td", { class: "select-cell" }, box),
    h("td", {}, statusPill(item.status)),
    h("td", { attrs: { title: item.last_ts ?? "" }, class: "num" }, ageLabel(item, context.nowMs)),
    h("td", { class: "col-project" }, item.project),
    h("td", {}, title),
    h("td", { class: "col-mark" }, markGlyph(item.mark)),
    h("td", { class: "col-actions" }, rowActions(item, context.perform, context.outcomes.get(item.id), context.isBusy)),
  );
  return isOpen ? [main, h("tr", { class: "detail-row" }, details(item))] : [main];
}

function groupRow(group: Group, count: number): HTMLTableRowElement {
  const status = GROUP_STATUS[group];
  const pill = statusPill(status);
  return h("tr", { attrs: { "data-group": group }, class: "group-row" }, h("th", { attrs: { colspan: COLUMN_COUNT, scope: "colgroup", title: STATUS_LABEL[status] } }, pill, h("span", { class: "group-count", text: String(count) })));
}

/** Group rows only while unsorted: the groups are the server's order, and a sort replaces it. */
export function renderTable(context: TableContext): HTMLElement {
  const body = h("tbody");
  if (context.query.sort.length === 0) {
    for (const run of groupRuns(context.items)) {
      body.append(groupRow(run.group, run.items.length), ...run.items.flatMap((item) => row(item, context)));
    }
  } else {
    body.append(...context.items.flatMap((item) => row(item, context)));
  }
  return h("div", { class: "table-scroll" }, h("table", { attrs: { "aria-label": label.table } }, head(context), body));
}
