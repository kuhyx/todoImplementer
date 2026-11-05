import type { Context } from "@/usage/context";

import { h } from "@/lib/dom";
import { loadContext } from "@/usage/api";
import { rankChart } from "@/usage/chart-bars";
import { col } from "@/usage/columns";
import { usd } from "@/usage/format";
import { makeTable } from "@/usage/table-element";
import { banner, tiles } from "@/usage/view-kit";

export async function contextView(context: Context, signal: AbortSignal): Promise<HTMLElement> {
  const data = await loadContext(context.filters(), signal);
  const rows = data.files.map((file) => ({ ...file, breaches: file.breaches.length, budgets: file.budgets.join(", "), history: file.history.length }));
  const over = data.files.filter((file) => file.status !== "ok");
  const costly = data.files.toSorted((a, b) => b.usd_per_day - a.usd_per_day).slice(0, 10);
  return h(
    "div",
    { class: "view" },
    tiles([
      { label: "Files", value: String(data.files.length) },
      { label: "Over a limit", value: String(over.length) },
      { label: "Standing cost", value: `${usd(data.files.reduce((sum, file) => sum + file.usd_per_day, 0))} / day` },
      { label: "Calls per day", value: String(Math.round(data.calls_per_day)) },
    ]),
    over.length > 0 ? banner("red", `${String(over.length)} of ${String(data.files.length)} always-loaded files are over a budget`) : banner("green", "Every listed file is inside its budget"),
    rankChart("Costliest files (USD per day)", costly.map((file) => ({ label: file.path.replace(/^.*\//v, ""), value: file.usd_per_day })), usd, 3),
    makeTable({
      columns: [
        col.link("path", "File", (row) => context.href("f", String(row.path))),
        col.tag("kind", "Kind"),
        col.tag("standing", "Loaded"),
        col.tag("status", "Status"),
        col.big("tokens", "Tokens"),
        col.big("bytes", "Bytes"),
        col.count("lines", "Lines"),
        col.money("usd_per_day", "USD / day"),
        col.count("breaches", "Breaches"),
        col.text("budgets", "Budgets"),
        col.count("history", "Versions"),
      ],
      context,
      id: "files",
      rows,
      title: "Context files",
    }),
  );
}
