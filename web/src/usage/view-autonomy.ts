import type { Autonomy } from "@/lib/schemas-autonomy";
import type { Context } from "@/usage/context";
import type { Tile } from "@/usage/view-kit";

import { h } from "@/lib/dom";
import { usage } from "@/lib/schemas";
import { getJson } from "@/usage/api";
import { barChart } from "@/usage/chart-bars";
import { color } from "@/usage/chart-scale";
import { compact } from "@/usage/format";
import { grid, note, section, tiles } from "@/usage/view-kit";

type Metric = Pick<Autonomy["criteria_failed"], "direction" | "target"> & { value: null | number };

/** Green when the value is on the right side of the target for its direction; grey while there is no value. */
export function levelOf(metric: Metric): "green" | "grey" | "red" {
  if (metric.value === null) return "grey";
  const isOnTarget = metric.direction === "up" ? metric.value >= metric.target : metric.value <= metric.target;
  return isOnTarget ? "green" : "red";
}

const WORD = { green: "on target", grey: "no data yet", red: "off target" } as const;
const percent = (value: number): string => `${String(value)}%`;

function tile(label: string, metric: Metric, detail: string, show: (value: number) => string): Tile {
  const level = levelOf(metric);
  const way = metric.direction === "up" ? "higher is better" : "lower is better";
  return {
    label,
    level,
    note: `${WORD[level]} · target ${show(metric.target)}, ${way}${detail}`,
    value: metric.value === null ? "—" : show(metric.value),
  };
}

function weekly(title: string, rows: { value: number; week: string }[], fmt: (value: number) => string, index: number): HTMLElement {
  return barChart({ fmt, labels: rows.map((row) => row.week.slice(5)), series: [{ color: color(index), name: title, values: rows.map((row) => row.value) }], title });
}

export async function autonomyView(_context: Context, signal: AbortSignal): Promise<HTMLElement> {
  const { autonomy: a } = await getJson("/api/usage", usage, signal);
  const done = a.done_unassisted;
  return h(
    "div",
    { class: "view" },
    note("How much of the work ran without kuhy. Ship is the intended gate and does not count as an intervention."),
    tiles([
      tile("Done unassisted", done, ` · ${String(done.count)} of ${String(done.finished)} finished cards`, percent),
      tile("Permissions asked", a.permission_asks, "", String),
      tile("Questions asked", a.questions_asked, "", String),
      tile("Criteria failed", a.criteria_failed, "", String),
    ]),
    grid(
      weekly("Done unassisted per week", done.weekly, percent, 0),
      weekly("Permissions asked per week", a.permission_asks.weekly, String, 1),
      weekly("Questions asked per week", a.questions_asked.weekly, String, 2),
      weekly("Criteria failed per week", a.criteria_failed.weekly, String, 3),
    ),
    section(
      "Where the numbers come from",
      note(
        `${compact(a.cards)} cards read, ${compact(a.backfilled)} of them from before the intervention record: for those, Send notes, spec answers, Spec OK and credits are rebuilt from disk; restarts, cancels and go clicks cannot be.`,
      ),
    ),
  );
}
