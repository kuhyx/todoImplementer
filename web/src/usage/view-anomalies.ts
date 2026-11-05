import type { Context } from "@/usage/context";

import { h } from "@/lib/dom";
import { loadAnomalies } from "@/usage/api";
import { rankChart } from "@/usage/chart-bars";
import { lineChart } from "@/usage/chart-line";
import { color } from "@/usage/chart-scale";
import { col } from "@/usage/columns";
import { usd } from "@/usage/format";
import { makeTable } from "@/usage/table-element";
import { banner, grid, section, short, tiles } from "@/usage/view-kit";

export async function anomaliesView(context: Context, signal: AbortSignal): Promise<HTMLElement> {
  const data = await loadAnomalies(context.filters(), signal);
  const { totals } = data;
  const session = (row: Record<string, unknown>): string => context.href("s", String(row.key));
  const table = (id: string, title: string, rows: Record<string, unknown>[], columns: ReturnType<typeof col.text>[]) =>
    section(title, makeTable({ columns, context, id, rows, title }));
  return h(
    "div",
    { class: "view" },
    banner(totals.spikes + totals.loops > 0 ? "red" : "green", data.caption),
    tiles([
      { label: "Spike days", value: String(totals.spikes) },
      { label: "Expensive sessions", value: `${String(totals.expensive)} (${usd(totals.expensive_usd)})` },
      { label: "Loops", value: String(totals.loops) },
    ]),
    grid(
      lineChart({ fmt: usd, labels: data.spikes.map((row) => row.day.slice(5)), series: [{ color: color(1), name: "Spend", values: data.spikes.map((row) => row.usd) }, { color: color(0), name: "Median", values: data.spikes.map((row) => row.median_usd) }], title: "Spike days against the median day" }),
      rankChart("Spend by category", data.category_totals.map((row) => ({ label: row.category, value: row.cost_usd })), usd, 2),
    ),
    table("spikes", "Spike days", data.spikes, [col.text("day", "Day"), col.money("usd", "USD"), col.money("median_usd", "Median"), col.count("ratio", "Ratio")]),
    table("expensive", "Expensive sessions", data.expensive.map((row) => ({ ...row, title: short(row.title) })), [col.link("title", "Session", session), col.tag("cwd", "Directory"), col.tag("day", "Day"), col.money("usd", "USD"), col.count("calls", "Calls")]),
    table("loops", "Repeated calls", data.loops, [col.link("name", "Tool", session), col.text("target", "Target"), col.count("repeats", "Repeats"), col.money("cost_usd", "USD")]),
    table("categories", "Costly calls by category", data.categories, [col.link("category", "Category", session), col.count("calls", "Calls"), col.money("cost_usd", "USD")]),
  );
}
