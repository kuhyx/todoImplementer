import type { Context } from "@/usage/context";

import { h } from "@/lib/dom";
import { loadLevers } from "@/usage/api";
import { lineChart } from "@/usage/chart-line";
import { color } from "@/usage/chart-scale";
import { col } from "@/usage/columns";
import { makeTable } from "@/usage/table-element";
import { grid, note, section } from "@/usage/view-kit";

const metricFormat = (value: number): string => (Math.abs(value) < 10 ? value.toFixed(2) : String(Math.round(value)));

export async function leversView(context: Context, signal: AbortSignal): Promise<HTMLElement> {
  const data = await loadLevers(context.filters(), signal);
  const charts = Object.entries(data.series).map(([metric, series], index) => {
    const points = series.daily.length > 1 ? series.daily : series.snapshots;
    return lineChart({ fmt: metricFormat, labels: points.map((point) => point.date.slice(5)), series: [{ color: color(index), name: metric, values: points.map((point) => point.value) }], title: metric.replaceAll("_", " ") });
  });
  return h(
    "div",
    { class: "view" },
    note(`Optimisation ideas and what they did. Daily series use a ${String(data.rolling_days)}-day rolling window; metrics without daily data show their snapshots.`),
    grid(...charts),
    section("Levers", makeTable({
      columns: [
        col.text("lever", "Lever"),
        col.tag("status", "Status"),
        col.tag("outcome", "Outcome"),
        col.tag("metric", "Metric"),
        col.count("baseline", "Baseline"),
        col.count("predicted", "Predicted"),
        col.count("actual", "Actual"),
        col.tag("date", "Date"),
        col.tag("source", "Source"),
        col.text("detail", "Detail"),
      ],
      context, id: "rows", rows: data.rows, title: "Levers",
    })),
  );
}
