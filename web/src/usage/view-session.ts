import type { Context } from "@/usage/context";

import { h } from "@/lib/dom";
import { loadSession } from "@/usage/api";
import { barChart } from "@/usage/chart-bars";
import { color } from "@/usage/chart-scale";
import { col } from "@/usage/columns";
import { compact, duration, stamp, usd } from "@/usage/format";
import { makeTable } from "@/usage/table-element";
import { link, section, short, tiles } from "@/usage/view-kit";

export async function sessionView(context: Context, signal: AbortSignal, key: string): Promise<HTMLElement> {
  const data = await loadSession(key, signal);
  const { session } = data;
  const prompts = data.prompts.map((prompt) => ({ ...prompt, text: short(prompt.text, 140) }));
  const timeline = prompts.toSorted((a, b) => a.idx - b.idx);
  const byTool = Object.groupBy(data.prompts.flatMap((prompt) => prompt.tools), (tool) => tool.name);
  const tools = Object.entries(byTool).map(([name, group = []]) => {
    return {
      calls: group.reduce((sum, tool) => sum + tool.calls, 0),
      carry_usd: group.reduce((sum, tool) => sum + tool.carry_usd, 0),
      name,
      result_tokens: group.reduce((sum, tool) => sum + tool.result_tokens, 0),
      usd: group.reduce((sum, tool) => sum + tool.usd, 0),
    };
  });
  const agents = [...data.unattributed, ...data.prompts.flatMap((prompt) => prompt.subagents)];
  return h(
    "div",
    { class: "view" },
    h("p", { class: "crumbs" }, link(context.href("sessions"), "Sessions"), ` / ${session.title}`),
    h("p", { class: "note", text: `${session.cwd ?? "—"} · ${stamp(session.first_ts)} to ${stamp(session.last_ts)} · ${session.final_tag ?? "no tag"}` }),
    tiles([
      { label: "Spend", value: usd(session.usd) },
      { label: "Main", value: usd(session.usd_main) },
      { label: "Subagents", value: usd(session.usd_sub) },
      { label: "Calls", value: compact(session.calls) },
      { label: "Prompts", value: String(session.prompts) },
      { label: "Active", value: duration(session.active_s) },
    ]),
    barChart({
      fmt: usd,
      labels: timeline.map((prompt) => `#${String(prompt.idx)}`),
      series: [
        { color: color(0), name: "Own", values: timeline.map((prompt) => prompt.usd_own) },
        { color: color(1), name: "Subagents", values: timeline.map((prompt) => prompt.usd_sub) },
      ],
      title: "Cost per prompt",
    }),
    barChart({
      fmt: compact,
      labels: data.stream.map((call) => String(call.idx)),
      series: [
        { color: color(0), name: "Fixed", values: data.stream.map((call) => call.fixed) },
        { color: color(1), name: "Accumulated", values: data.stream.map((call) => call.accumulated) },
      ],
      title: "Context per call",
    }),
    section("Calls by trigger", makeTable({
      columns: [col.tag("trigger", "Trigger"), col.count("calls", "Calls"), col.money("usd", "USD"), col.pct("share", "Share"), col.big("output", "Output tokens"), col.big("context", "Context read"), col.big("accumulated", "Accumulated")],
      context, id: "classes", rows: data.classes, title: "Calls by trigger",
    })),
    section("Calls", makeTable({
      columns: [col.count("idx", "#"), col.when("ts", "Time"), col.count("prompt_idx", "Prompt"), col.tag("trigger", "Trigger"), col.big("context", "Context"), col.big("fixed", "Fixed"), col.big("accumulated", "Accumulated"), col.big("output", "Output"), col.money("usd", "USD")],
      context, id: "stream", rows: data.stream, title: "Calls",
    })),
    section("Prompts", makeTable({
      columns: [col.count("idx", "#"), col.when("ts", "Time"), col.text("text", "Prompt"), col.money("usd", "USD"), col.money("usd_own", "Own"), col.money("usd_sub", "Subagents"), col.count("calls", "Calls"), col.secs("active_s", "Active"), col.secs("wall_s", "Wall")],
      context, id: "prompts", rows: prompts, title: "Prompts",
    })),
    section("Tools", makeTable({
      columns: [col.text("name", "Tool"), col.count("calls", "Calls"), col.big("result_tokens", "Result tokens"), col.money("usd", "USD"), col.money("carry_usd", "Carry USD")],
      context, id: "tools", rows: tools, title: "Tools",
    })),
    section("Subagents", makeTable({
      columns: [col.text("description", "Task"), col.tag("agent_type", "Type"), col.tag("model", "Model"), col.count("depth", "Depth"), col.money("usd", "USD"), col.count("calls", "Calls"), col.secs("wall_s", "Wall")],
      context, id: "subagents", rows: agents, title: "Subagents",
    })),
  );
}
