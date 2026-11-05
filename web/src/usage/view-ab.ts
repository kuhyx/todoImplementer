import type { Context } from "@/usage/context";
import type { AbExperiment } from "@/usage/schemas-panels";

import { h } from "@/lib/dom";
import { loadAb } from "@/usage/api";
import { intervalChart } from "@/usage/chart-intervals";
import { col } from "@/usage/columns";
import { share } from "@/usage/format";
import { makeTable } from "@/usage/table-element";
import { banner, note, section } from "@/usage/view-kit";

function experiment(context: Context, id: string, title: string, data: AbExperiment): HTMLElement {
  const diffs = Object.entries(data.diffs ?? {}).map(([label, d]) => ({ diff: d.diff, high: d.high, label, low: d.low }));
  const arms = Object.entries(data.arms).map(([name, arm]) => `${name}: n=${String((arm).n)}`).join(" · ");
  const unjoined = data.unjoined === undefined ? undefined : `${String(data.unjoined)} unjoined`;
  return section(
    title,
    banner(data.banner.level, data.banner.text),
    note(unjoined === undefined ? arms : `${arms} · ${unjoined}`),
    intervalChart("Sonnet minus Opus, with confidence interval", diffs, (v) => share(v)),
    makeTable({
      columns: [col.text("measure", "Measure"), col.text("sonnet", "Sonnet"), col.text("opus", "Opus"), col.text("difference", "Difference")],
      context, id, rows: data.metrics ?? [], title,
    }),
  );
}

export async function abView(context: Context, signal: AbortSignal): Promise<HTMLElement> {
  const data = await loadAb(context.filters(), signal);
  return h("div", { class: "view" }, experiment(context, "metrics", "Judgment agents", data), data.build === undefined ? null : experiment(context, "build", "Build agents (all time)", data.build));
}
