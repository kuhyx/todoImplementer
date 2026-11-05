import type { Context } from "@/usage/context";
import type { SessionRow } from "@/usage/schemas";

import { h } from "@/lib/dom";
import { loadSessions } from "@/usage/api";
import { col } from "@/usage/columns";
import { usd } from "@/usage/format";
import { makeTable } from "@/usage/table-element";
import { tiles } from "@/usage/view-kit";

const modelNames = (models: SessionRow["models"]): string => Object.keys(models).map((name) => name.replace(/^claude-/v, "")).toSorted((a, b) => a.localeCompare(b)).join(", ");

export async function sessionsView(context: Context, signal: AbortSignal): Promise<HTMLElement> {
  const { sessions } = await loadSessions(context.filters(), signal);
  const rows = sessions.map((row) => ({ ...row, models: modelNames(row.models) }));
  const total = sessions.reduce((sum, row) => sum + row.usd, 0);
  return h(
    "div",
    { class: "view" },
    tiles([
      { label: "Sessions", value: String(sessions.length) },
      { label: "Spend", value: usd(total) },
      { label: "Subagent spend", value: usd(sessions.reduce((sum, row) => sum + row.usd_sub, 0)) },
    ]),
    makeTable({
      columns: [
        col.link("title", "Title", (row) => context.href("s", String(row.key))),
        col.text("cwd", "Directory"),
        col.when("last_ts", "Last active"),
        col.money("usd", "USD"),
        col.money("usd_main", "Main"),
        col.money("usd_sub", "Subagents"),
        col.count("calls", "Calls"),
        col.count("prompts", "Prompts"),
        col.count("subagents", "Agents"),
        col.secs("active_s", "Active"),
        col.secs("wall_s", "Wall"),
        col.tag("final_tag", "Tag"),
        col.text("models", "Models"),
      ],
      context,
      id: "sessions",
      rows,
      title: "Sessions",
    }),
  );
}
