/** Free-model issues grouped by phase and model: counts first, the raw jsonl lines on expand. */
import type { Track } from "@/lib/schemas-track";
import type { Expand } from "@/track/track-kids";

import { icon } from "@/components/icons";
import { h } from "@/lib/dom";
import { routes } from "@/lib/routes";
import { stat } from "@/track/track-kit";

const LOG_LABEL = "Issue log";

function group(item: Track["issues"]["groups"][number], expand: Expand): HTMLElement {
  const key = `issue:${item.phase}:${item.model ?? ""}`;
  const isOpen = expand.has(key);
  return h(
    "li",
    { attrs: { "data-open": String(isOpen), "data-phase": item.phase }, class: "t-group" },
    h(
      "button",
      {
        attrs: { "aria-expanded": isOpen, type: "button" },
        class: "t-group-main",
        on: { click: () => { expand.toggle(key); } },
      },
      h("code", { class: "t-phase", text: item.phase }),
      h("code", { class: "t-model", text: item.model ?? "–" }),
      stat("issue", "Issues", item.count),
      item.fixed > 0 && stat("fixed", "Fixed by the manager", item.fixed),
    ),
    isOpen && h("pre", { class: "t-lines", text: item.lines.join("\n") }),
  );
}

export function renderIssues(issues: Track["issues"], id: string, expand: Expand): HTMLElement {
  return h(
    "section",
    { attrs: { "aria-label": "Free-model issues" }, class: "t-issues" },
    h(
      "div",
      { class: "t-issues-head" },
      stat("issue", "Free-model issues", issues.total),
      h("a", { attrs: { "aria-label": LOG_LABEL, href: routes.issuesPage(id), rel: "noopener", target: "_blank", title: LOG_LABEL }, class: "btn icon-btn t-link" }, icon("log")),
    ),
    h("ul", { class: "t-groups" }, ...issues.groups.map((item) => group(item, expand))),
  );
}
