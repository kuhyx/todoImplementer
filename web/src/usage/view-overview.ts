import type { Context } from "@/usage/context";
import type { DailyRow } from "@/usage/schemas";

import { h } from "@/lib/dom";
import { loadOverview } from "@/usage/api";
import { barChart } from "@/usage/chart-bars";
import { lineChart } from "@/usage/chart-line";
import { color } from "@/usage/chart-scale";
import { compact, share, usd } from "@/usage/format";
import { makeTable } from "@/usage/table-element";
import { grid, section, tiles } from "@/usage/view-kit";

const dayLabel = (day: string): string => day.slice(5);
const percent = (value: number): string => `${(value * 100).toFixed(0)}%`;

export async function overviewView(context: Context, signal: AbortSignal): Promise<HTMLElement> {
  const data = await loadOverview(context.filters(), signal);
  const days = data.daily.map((row) => dayLabel(row.day));
  const shares: [string, keyof DailyRow][] = [["Subagents", "sub_share"], ["Opus", "opus_share"], ["Over budget", "over_share"], ["Home dir", "home_share"]];
  const { tiles: t } = data;
  return h(
    "div",
    { class: "view" },
    tiles([
      { label: "Spend", value: usd(t.usd) },
      { label: "Per day", value: usd(t.usd_per_day) },
      { label: "Calls", value: compact(t.calls) },
      { label: "Per call", value: usd(t.usd_per_call) },
      { label: "Sessions", value: compact(t.sessions) },
      { label: "Active", value: `${t.active_h.toFixed(1)} h` },
    ]),
    grid(
      barChart({ fmt: usd, labels: days, series: [{ color: color(0), name: "USD", values: data.daily.map((row) => row.usd) }], title: "Spend per day" }),
      lineChart({ fmt: compact, labels: days, series: [{ color: color(1), name: "Calls", values: data.daily.map((row) => row.calls) }], title: "Calls per day" }),
      barChart({ fmt: usd, labels: data.weekly.map((row) => row.week), series: [{ color: color(0), name: "USD", values: data.weekly.map((row) => row.usd) }], title: "Spend per week" }),
      lineChart({ fmt: compact, labels: data.prompts.map((row) => dayLabel(row.day)), series: [{ color: color(2), name: "Prompts", values: data.prompts.map((row) => row.prompts) }], title: "Prompts per day" }),
    ),
    section("Where it goes", grid(...shares.map(([name, key], index) => lineChart({ fmt: percent, labels: days, series: [{ color: color(index), name, values: data.daily.map((row) => row[key] as null | number) }], title: `${name} share of spend` })))),
    section(
      "Daily",
      makeTable({
        columns: [
          { key: "day", kind: "text", label: "Day" },
          { key: "usd", kind: "number", label: "USD", show: (v) => usd(v as number) },
          { key: "calls", kind: "number", label: "Calls" },
          { key: "usd_per_call", kind: "number", label: "USD / call", show: (v) => usd(v as null | number) },
          { key: "sub_share", kind: "number", label: "Subagents", show: (v) => share(v as null | number) },
          { key: "opus_share", kind: "number", label: "Opus", show: (v) => share(v as null | number) },
          { key: "over_share", kind: "number", label: "Over budget", show: (v) => share(v as null | number) },
          { key: "home_share", kind: "number", label: "Home dir", show: (v) => share(v as null | number) },
        ],
        context,
        id: "daily",
        rows: data.daily,
        title: "Daily spend",
      }),
    ),
  );
}
