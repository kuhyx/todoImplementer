import type { Context } from "@/usage/context";

import { h } from "@/lib/dom";
import { loadItems } from "@/usage/api";
import { rankChart } from "@/usage/chart-bars";
import { col } from "@/usage/columns";
import { usd } from "@/usage/format";
import { makeTable } from "@/usage/table-element";
import { grid, note, section, tiles } from "@/usage/view-kit";

export async function itemsView(context: Context, signal: AbortSignal): Promise<HTMLElement> {
  const data = await loadItems(context.filters(), signal);
  const items = new Set(data.items.map((row) => row.item));
  const table = (id: string, title: string, rows: Record<string, unknown>[], first: [string, string]) =>
    section(title, makeTable({ columns: [col.text(first[0], first[1]), col.money("usd", "USD"), col.count("calls", "Calls"), col.count("sessions", "Sessions")], context, id, rows, title }));
  return h(
    "div",
    { class: "view" },
    note("Cost of the Claude sessions todoImplementer ran, joined to the todo item, repo and stage that started them."),
    tiles([
      { label: "Spend", value: usd(data.total_usd) },
      { label: "Items", value: String(items.size) },
      { label: "Repos", value: String(data.repos.length) },
      { label: "USD per shipped part", value: usd(data.compare.usd_per_part) },
      { label: "Manual USD per session", value: usd(data.compare.usd_per_session) },
      { label: "Manual USD per day", value: usd(data.compare.usd_per_day) },
    ]),
    section("Per shipped part", makeTable({
      columns: [col.text("part", "Part"), col.tag("repo", "Repo"), col.count("cycle", "Cycle"), col.text("at", "Shipped"), col.count("parts", "Parts"), col.count("sessions", "Sessions"), col.money("cycle_usd", "Cycle USD"), col.money("usd", "USD")],
      context, id: "shipped", rows: data.shipped, title: "Cost per shipped part",
    })),
    section("Manual per day", makeTable({
      columns: [col.text("day", "Day"), col.count("sessions", "Sessions"), col.count("calls", "Calls"), col.money("usd", "USD"), col.money("mean_usd", "USD per session")],
      context, id: "manual", rows: data.manual, title: "Manual cost per day",
    })),
    grid(
      rankChart("USD per repo", data.repos.map((row) => ({ label: row.repo, value: row.usd })), usd),
      rankChart("USD per stage", data.stages.map((row) => ({ label: row.stage, value: row.usd })), usd, 1),
    ),
    section("Per item and stage", makeTable({
      columns: [col.text("item", "Item"), col.tag("repo", "Repo"), col.tag("stage", "Stage"), col.money("usd", "USD"), col.count("calls", "Calls"), col.count("sessions", "Sessions")],
      context, id: "items", rows: data.items, title: "Cost per item",
    })),
    grid(table("repos", "Per repo", data.repos, ["repo", "Repo"]), table("stages", "Per stage", data.stages, ["stage", "Stage"])),
  );
}
