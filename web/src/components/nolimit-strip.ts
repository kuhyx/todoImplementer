import type { NoLimit } from "@/lib/schemas-nolimit";

/**
 * The no-limit runner's row (DOCS-nolimit.md): a wrench while no Claude route runs, the repo it visited last and
 * that visit's result as an icon. Words live only in title and aria-label (textgate); dimmed while it rests.
 */
import { icon, type IconName } from "@/components/icons";
import { h } from "@/lib/dom";
import { formatAgo } from "@/lib/format";

type Result = NonNullable<NoLimit["result"]>;

const RESULT: Record<Result, { icon: IconName; label: string; tone: string }> = {
  deployed: { icon: "install", label: "gate green, fixes pushed and deployed", tone: "ok" },
  green: { icon: "done", label: "gate green, nothing pushed", tone: "ok" },
  pushed: { icon: "escalated", label: "gate green, fixes pushed", tone: "ok" },
  readonly: { icon: "eye", label: "no gate, lint only", tone: "ok" },
  red: { icon: "failed", label: "a step failed, tickets filed", tone: "danger" },
  slow: { icon: "hourglass", label: "a step ran past 60 s, ticket filed", tone: "warn" },
  stopped: { icon: "close", label: "stopped: a Claude route opened", tone: "unknown" },
};

export function renderNoLimit(row: NoLimit | undefined, now: number): HTMLElement | null {
  if (row === undefined || (!row.active && row.repo === null)) return null;
  const state = row.active ? "No-limit runner: on, no Claude route" : "No-limit runner: resting";
  const found = row.result === null ? null : RESULT[row.result];
  const last = found === null || row.repo === null ? "" : `; last: ${row.repo}, ${found.label}, ${formatAgo(row.at, now)}`;
  const label = `${state}${last}`;
  return h(
    "div",
    { attrs: { "aria-label": label, "data-active": String(row.active), role: "group", title: label }, class: "free-strip nolimit-strip" },
    h("span", { attrs: { "data-kind": "runner" }, class: "f-chip" }, icon("fixed")),
    row.repo !== null && h("span", { class: "f-chip nl-repo", text: row.repo }),
    found !== null && h("span", { attrs: { "data-result": row.result ?? "", "data-tone": found.tone }, class: "f-chip" }, icon(found.icon)),
  );
}
