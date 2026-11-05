/** <usage-table>: a sortable, filterable, searchable table whose state lives in the URL hash (R3). */
import type { Context } from "@/usage/context";

import { h } from "@/lib/dom";
import { countText, label } from "@/usage/labels";
import { applyTable, type Column, cycleSort, distinct, EMPTY_TABLE, PAGE, type Row, shown, type SortKey, type TableState } from "@/usage/table-model";

export interface TableConfig<R extends Row> {
  columns: Column<R>[];
  context: Context;
  id: string;
  rows: R[];
  title: string;
}

const ENUM_MAX = 30;
const ENUM_CHARS = 40;
const ARROW = { ascending: "▲", descending: "▼", none: "" } as const;
const isNumber = (column: Column<never>): boolean => column.kind === "number";

function sortOrder(at: SortKey | undefined): keyof typeof ARROW {
  if (at === undefined) return "none";
  return at.desc ? "descending" : "ascending";
}

export class UsageTable<R extends Row = Row> extends HTMLElement {
  private readonly body = h("tbody");
  private readonly count = h("span", { class: "ut-count" });
  private readonly heads = new Map<string, HTMLTableCellElement>();
  private readonly more = h("button", { attrs: { type: "button" }, class: "btn" });
  private clear = this.more;
  private config!: TableConfig<R>;
  private search = h("input");
  private state: TableState = EMPTY_TABLE;

  private change(next: TableState): void {
    this.state = next;
    this.config.context.write(this.config.id, next);
    this.refresh();
  }

  private reset(): void {
    this.search.value = "";
    for (const input of this.querySelectorAll<HTMLInputElement | HTMLSelectElement>("[data-f]")) input.value = "";
    this.change(EMPTY_TABLE);
  }

  private header(column: Column<R>): HTMLTableCellElement {
    const button = h("button", {
      attrs: { type: "button" },
      class: "ut-sort",
      on: { click: (event) => { this.change({ ...this.state, sort: cycleSort(this.state.sort, column.key, event.shiftKey) }); } },
      text: column.label,
    });
    const cell = h("th", { attrs: { "data-key": column.key, scope: "col" }, class: isNumber(column) ? "num" : "" }, button);
    this.heads.set(column.key, cell);
    return cell;
  }

  private setFilter(key: string, rule: string): void {
    const rest = Object.fromEntries(Object.entries(this.state.filters).filter(([name]) => name !== key));
    this.change({ ...this.state, filters: rule === "" ? rest : { ...rest, [key]: rule } });
  }

  private filter(column: Column<R>): HTMLTableCellElement {
    const key = column.key;
    const rule = this.state.filters[key] ?? "";
    const name = `${label.filter} ${column.label}`;
    const values = column.kind === "enum" ? distinct(this.config.rows, key) : [];
    const cell = h("td", { class: "ut-f" });
    if (values.length > 1 && values.length <= ENUM_MAX && values.every((value) => value.length <= ENUM_CHARS)) {
      const select = h("select", { attrs: { "aria-label": name, "data-f": key }, on: { change: () => { this.setFilter(key, select.value === "" ? "" : `=${select.value}`); } } },
        h("option", { attrs: { value: "" }, text: label.all }), ...values.map((value) => h("option", { attrs: { value }, text: value })));
      select.value = rule.replace(/^=/v, "");
      cell.append(select);
    } else if (isNumber(column)) {
      const [lo = "", hi = ""] = rule.split("..", 2);
      const bound = (kind: "max" | "min", value: string): HTMLInputElement =>
        h("input", { attrs: { "aria-label": `${name} ${kind}`, "data-f": `${key}.${kind}`, inputmode: "decimal", placeholder: kind, value } });
      const low = bound("min", lo);
      const high = bound("max", hi);
      const both = (): void => { this.setFilter(key, low.value === "" && high.value === "" ? "" : `${low.value}..${high.value}`); };
      low.addEventListener("input", both);
      high.addEventListener("input", both);
      cell.append(low, high);
    } else {
      const input = h("input", { attrs: { "aria-label": name, "data-f": key, value: rule.replace(/^~/v, "") }, on: { input: () => { this.setFilter(key, input.value === "" ? "" : `~${input.value}`); } } });
      cell.append(input);
    }
    return cell;
  }

  private row(row: R): HTMLTableRowElement {
    return h("tr", {}, ...this.config.columns.map((column) => {
      const text = shown(column, row);
      const content = column.href === undefined ? text : h("a", { attrs: { href: column.href(row) }, text });
      return h("td", { class: isNumber(column) ? "num" : "" }, content);
    }));
  }

  private refresh(): void {
    const rows = applyTable(this.config.rows, this.config.columns, this.state);
    const limit = this.state.limit ?? PAGE;
    const visible = limit === 0 ? rows : rows.slice(0, limit);
    const none = h("tr", {}, h("td", { attrs: { colspan: this.config.columns.length }, class: "ut-empty", text: label.empty }));
    this.body.replaceChildren(...(visible.length === 0 ? [none] : visible.map((row) => this.row(row))));
    for (const [key, head] of this.heads) {
      const at = this.state.sort.find((s) => s.key === key);
      const order = sortOrder(at);
      head.setAttribute("aria-sort", order);
      head.dataset.arrow = ARROW[order];
    }
    this.count.textContent = countText(visible.length, rows.length, this.config.rows.length);
    this.more.hidden = rows.length <= PAGE;
    this.more.textContent = limit === 0 ? `${label.showFirst} ${String(PAGE)}` : `${label.showAll} ${String(rows.length)}`;
    this.clear.hidden = this.state.q === "" && this.state.sort.length === 0 && this.state.limit === null && Object.keys(this.state.filters).length === 0;
  }

  configure(config: TableConfig<R>): void {
    this.config = config;
    this.state = config.context.read(config.id);
    this.search = h("input", {
      attrs: { "aria-label": `${label.search} ${config.title}`, autocomplete: "off", placeholder: label.searchHint, type: "search", value: this.state.q },
      on: { input: () => { this.change({ ...this.state, q: this.search.value }); } },
    });
    this.clear = h("button", {
      attrs: { type: "button" },
      class: "btn",
      on: { click: () => { this.reset(); } },
      text: label.reset,
    });
    this.more.addEventListener("click", () => { this.change({ ...this.state, limit: this.state.limit === 0 ? PAGE : 0 }); });
    const head = h("thead", {}, h("tr", {}, ...config.columns.map((c) => this.header(c))), h("tr", { class: "ut-filters" }, ...config.columns.map((c) => this.filter(c))));
    this.setAttribute("class", "ut");
    this.replaceChildren(
      h("div", { attrs: { role: "search" }, class: "ut-bar" }, this.search, this.count, this.clear, this.more),
      h("div", { class: "ut-scroll" }, h("table", { attrs: { "aria-label": config.title } }, head, this.body)),
    );
    this.refresh();
  }
}

export function defineTable(): void {
  if (customElements.get("usage-table") === undefined) customElements.define("usage-table", UsageTable);
}

export function makeTable<R extends Row>(config: TableConfig<R>): UsageTable<R> {
  defineTable();
  const table = document.createElement("usage-table") as UsageTable<R>;
  table.configure(config);
  return table;
}
