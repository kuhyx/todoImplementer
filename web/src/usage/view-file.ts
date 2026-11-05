import type { Context } from "@/usage/context";
import type { ContextFile } from "@/usage/schemas";

import { h } from "@/lib/dom";
import { loadContext, loadFile } from "@/usage/api";
import { lineChart } from "@/usage/chart-line";
import { color } from "@/usage/chart-scale";
import { col } from "@/usage/columns";
import { cellText, compact, stamp, usd } from "@/usage/format";
import { makeTable } from "@/usage/table-element";
import { banner, link, note, section, tiles } from "@/usage/view-kit";

function rowSections(context: Context, row: ContextFile | undefined): HTMLElement[] {
  if (row === undefined) return [];
  return [
    tiles([
      { label: "Tokens", value: compact(row.tokens) },
      { label: "Bytes", value: compact(row.bytes) },
      { label: "Lines", value: cellText(row.lines) },
      { label: "Standing cost", value: `${usd(row.usd_per_day)} / day` },
    ]),
    banner(row.status === "ok" ? "green" : "red", row.status),
    makeTable({
      columns: [col.text("measure", "Measure"), col.count("value", "Value"), col.count("limit", "Limit"), col.tag("hard", "Hard"), col.text("why", "Why")],
      context, id: "breaches", rows: row.breaches, title: "Budget breaches",
    }),
  ];
}

export async function fileView(context: Context, signal: AbortSignal, path: string): Promise<HTMLElement> {
  const [detail, panel] = await Promise.all([loadFile(path, signal), loadContext(context.filters(), signal)]);
  const row = panel.files.find((file) => file.path === path);
  const history = row?.history ?? [];
  return h(
    "div",
    { class: "view" },
    h("p", { class: "crumbs" }, link(context.href("context"), "Context files"), ` / ${detail.path}`),
    note(detail.kind),
    ...rowSections(context, row),
    history.length > 1 ? lineChart({ fmt: compact, labels: history.map((entry) => stamp(entry.ts).slice(0, 10)), series: [{ color: color(0), name: "Bytes", values: history.map((entry) => entry.bytes) }], title: "Size over time" }) : null,
    section("Git history", h("ul", { class: "log" }, ...detail.git_log.map((line) => h("li", { text: line })))),
    section("Content", h("pre", { class: "content", text: detail.content ?? "(not readable)" })),
  );
}
