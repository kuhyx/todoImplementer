import type { Context } from "@/usage/context";
import type { Row } from "@/usage/table-model";

import { h } from "@/lib/dom";
import { loadGeneric, loadIndex } from "@/usage/api";
import { inferColumns } from "@/usage/columns";
import { makeTable } from "@/usage/table-element";
import { link, note, section, tiles } from "@/usage/view-kit";

const isRows = (value: unknown): value is Row[] => Array.isArray(value) && value.length > 0 && value.every((row) => typeof row === "object" && row !== null && !Array.isArray(row));

export async function moreIndexView(context: Context, signal: AbortSignal): Promise<HTMLElement> {
  const index = await loadIndex(signal);
  const shown = new Set(["ab", "anomalies", "context", "efficiency", "levers", "overview", "sessions"]);
  return h(
    "div",
    { class: "view" },
    note("Panels without a dedicated view: every list in them is a sortable, filterable table."),
    h("ul", { class: "panel-list" }, ...index.panels.filter((panel) => !shown.has(panel.name)).map((panel) => h("li", {}, link(context.href("more", panel.name), panel.title)))),
  );
}

/** Any panel: scalar fields become tiles, every list of objects a table. */
export async function genericView(context: Context, signal: AbortSignal, name: string): Promise<HTMLElement> {
  const data = await loadGeneric(name)(context.filters(), signal);
  const scalars = Object.entries(data).filter(([key, value]) => key !== "filters" && (typeof value === "number" || typeof value === "string"));
  const lists = Object.entries(data).filter((entry): entry is [string, Row[]] => isRows(entry[1]));
  return h(
    "div",
    { class: "view" },
    h("p", { class: "crumbs" }, link(context.href("more"), "More panels"), ` / ${name}`),
    scalars.length > 0 ? tiles(scalars.map(([key, value]) => ({ label: key.replaceAll("_", " "), value: String(value) }))) : null,
    ...lists.map(([key, rows]) => section(key.replaceAll("_", " "), makeTable({ columns: inferColumns(rows), context, id: key, rows, title: key }))),
  );
}
