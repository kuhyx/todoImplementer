import type { Context } from "@/usage/context";
import type { WeekRow } from "@/usage/schemas-panels";

import { h } from "@/lib/dom";
import { loadEfficiency } from "@/usage/api";
import { inferColumns } from "@/usage/columns";
import { makeTable } from "@/usage/table-element";
import { note, section } from "@/usage/view-kit";

export async function efficiencyView(context: Context, signal: AbortSignal): Promise<HTMLElement> {
  const data = await loadEfficiency(context.filters(), signal);
  const tables: [string, string, undefined | WeekRow[]][] = [
    ["done", "Spend per finished session", data.done],
    ["commits", "Spend per surviving commit", data.commits],
    ["estimate", "Spend per estimated call", data.estimate],
    ["notes_weekly", "Notes per week", data.notes_weekly],
    ["notes", "Spend per todo note", data.notes],
  ];
  return h(
    "div",
    { class: "view" },
    ...tables.map(([id, title, rows = []]) => section(title, note(data.captions[id.replace("_weekly", "")] ?? ""), makeTable({ columns: inferColumns(rows), context, id, rows, title }))),
  );
}
