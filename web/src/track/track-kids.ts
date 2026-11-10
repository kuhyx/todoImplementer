/** One row per child: status, repo, stage, elapsed, issues, resting reason, retries; the last issue expands. */
import type { TrackKid } from "@/lib/schemas-track";

import { icon } from "@/components/icons";
import { badge, STATUS_ICON, VERDICT_ICON } from "@/components/umbrella";
import { h } from "@/lib/dom";
import { routes } from "@/lib/routes";
import { formatSpan, restingStat, STAGE_ICON, stat } from "@/track/track-kit";

/** Which rows and groups are open; the view keeps it across re-renders. */
export interface Expand {
  has: (key: string) => boolean;
  toggle: (key: string) => void;
}

const FEED_LABEL = "Live feed (opens the umbrella)";
const LOG_LABEL = "Worker log";

function issueLine(kid: TrackKid): string {
  const last = kid.last_issue;
  if (last === null) return "";
  const model = last.model === null ? "" : ` · ${last.model}`;
  return `${last.phase}${model}: ${last.symptom}`;
}

function detail(kid: TrackKid): HTMLElement {
  const last = kid.last_issue;
  return h(
    "div",
    { class: "t-detail" },
    last !== null && h("code", { class: "t-issue", text: issueLine(kid) }),
    kid.error !== null && h("p", { class: "t-error", text: kid.error }),
  );
}

function links(kid: TrackKid, umbrella: string): HTMLElement {
  const log = h("a", { attrs: { "aria-label": LOG_LABEL, href: routes.workerLog(umbrella, kid.id), rel: "noopener", target: "_blank", title: LOG_LABEL }, class: "btn icon-btn t-link" }, icon("log"));
  const feed = h("a", { attrs: { "aria-label": FEED_LABEL, href: `#umbrella=${umbrella}&task=${umbrella}`, title: FEED_LABEL }, class: "btn icon-btn t-link" }, icon("running"));
  return h("span", { class: "t-links" }, kid.log && log, feed);
}

function row(kid: TrackKid, umbrella: string, now: number, expand: Expand): HTMLElement {
  const hasDetail = kid.last_issue !== null || kid.error !== null;
  const isOpen = hasDetail && expand.has(kid.id);
  const summary = h(
    "button",
    {
      attrs: { "aria-expanded": hasDetail ? isOpen : null, disabled: !hasDetail, title: issueLine(kid) || kid.title, type: "button" },
      class: "t-kid-main",
      on: { click: () => { expand.toggle(kid.id); } },
    },
    badge(STATUS_ICON[kid.status], kid.status.replaceAll("_", " ")),
    h("code", { class: "t-repo", text: kid.repo }),
    kid.stage !== null && stat(STAGE_ICON[kid.stage], `Stage ${kid.stage.replaceAll("_", " ")}`, undefined, { "data-stage": kid.stage }),
    kid.elapsed !== null && stat("queued", "Elapsed", formatSpan(kid.elapsed)),
    kid.issues > 0 && stat("issue", "Free-model issues", kid.issues),
    kid.resting !== null && restingStat(kid.resting, now),
    kid.free === true && stat("free", "Free worker"),
    kid.attempts > 0 && stat("retry", "Worker runs", kid.attempts),
    kid.killed > 0 && stat("killed", "Worker runs killed by a signal", kid.killed),
    kid.verdict !== null && badge(VERDICT_ICON[kid.verdict], kid.verdict, undefined, { "data-verdict": kid.verdict }),
  );
  return h(
    "li",
    { attrs: { "data-id": kid.id, "data-open": String(isOpen), "data-status": kid.status }, class: "t-kid" },
    h("div", { class: "t-kid-row" }, summary, links(kid, umbrella)),
    isOpen && detail(kid),
  );
}

export function renderKids(kids: TrackKid[], umbrella: string, now: number, expand: Expand): HTMLElement {
  return h("ul", { attrs: { "aria-label": "Children" }, class: "t-kids" }, ...kids.map((kid) => row(kid, umbrella, now, expand)));
}

