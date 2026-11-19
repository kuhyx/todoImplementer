import type { Status, UmbrellaCounts } from "@/lib/schemas-common";
import type { UmbrellaDetail, UmbrellaRow } from "@/lib/schemas-umbrella";

/** Umbrella notes: child progress on the card and per-child rows in the drawer. Icons and numbers only; names are aria-label and title. */
import { icon, type IconName } from "@/components/icons";
import { waitsBadge } from "@/components/repo-parts";
import { h } from "@/lib/dom";
import { routes } from "@/lib/routes";
import { trackLink } from "@/track/track-link";

type Bucket = "done" | "failed" | "queued" | "running";
const BUCKETS: readonly [Bucket, IconName, string][] = [
  ["done", "check", "Done"],
  ["running", "running", "Running"],
  ["queued", "queued", "Queued"],
  ["failed", "failed", "Failed"],
];
/** The glyph of a child's own server-computed status (display only: the status is the server's). */
export const STATUS_ICON: Record<Status, IconName> = {
  backlog: "queued",
  cancelled: "failed",
  done: "check",
  done_manually: "check",
  needs_you: "failed",
  paused_limit: "queued",
  queued: "queued",
  shipping: "running",
  waiting_phone_update: "queued",
  working: "running",
  yours: "failed",
};
type Verdict = NonNullable<UmbrellaRow["verdict"]>;
export const VERDICT_ICON: Record<Verdict, IconName> = { clean: "check", coached: "coached", escalate: "escalated", fixed: "fixed" };

/** One icon with an optional number; the name is the accessible label and the tooltip. */
export function badge(name: IconName, label: string, value?: number, attributes: Record<string, string> = {}): HTMLElement {
  const text = value === undefined ? label : `${label} ${String(value)}`;
  return h(
    "span",
    { attrs: { "aria-label": text, role: "img", title: text, ...attributes }, class: "u-badge" },
    icon(name),
    value !== undefined && h("span", { class: "u-num", text: String(value) }),
  );
}

/** Card line: a counter per non-empty bucket, the next round width and the free-model issue count. */
export function umbrellaProgress(counts: UmbrellaCounts): HTMLElement {
  return h(
    "span",
    { attrs: { "data-umbrella": "" }, class: "u-progress" },
    ...BUCKETS.filter(([bucket]) => counts[bucket] > 0).map(([bucket, name, label]) => badge(name, label, counts[bucket], { "data-bucket": bucket })),
    badge("width", "Round width", counts.width),
    counts.issues > 0 && badge("issue", "Free-model issues", counts.issues),
  );
}

function renderRow(row: UmbrellaRow): HTMLElement {
  return h(
    "li",
    { attrs: { "data-id": row.id, "data-status": row.status }, class: "u-row" },
    badge(STATUS_ICON[row.status], row.status.replaceAll("_", " ")),
    h("code", { class: "u-repo", text: row.repo }),
    row.round !== null && badge("width", "Round", row.round),
    row.verdict !== null && badge(VERDICT_ICON[row.verdict], row.verdict, undefined, { "data-verdict": row.verdict }),
    row.waits_on != null && waitsBadge(row.waits_on),
    row.free === true && badge("free", "Free worker"),
    row.issues > 0 && badge("issue", "Free-model issues", row.issues),
    row.error !== null && h("span", { class: "u-error", text: row.error }),
  );
}

/** Drawer block: the round widths in order (marked when the round doubled the width) and a row per child. */
export function renderUmbrella(detail: UmbrellaDetail, id: string): HTMLElement {
  const total = detail.rows.reduce((sum, row) => sum + row.issues, 0);
  return h(
    "section",
    { attrs: { "aria-label": "Umbrella", "data-umbrella-detail": "" }, class: "block u-detail" },
    h(
      "p",
      { class: "u-rounds" },
      badge("width", "Next round width", detail.width),
      ...detail.rounds.map((round) =>
        h("span", { attrs: { "data-doubled": String(round.next > round.width), title: `Round ${String(round.n)}` }, class: "u-round", text: String(round.width) }),
      ),
      trackLink(`#umbrella=${id}`),
      total > 0 && h("a", { attrs: { "aria-label": "Free-model issue log", href: routes.issues(id), rel: "noopener", target: "_blank", title: "Free-model issue log" }, class: "u-issues" }, icon("issue"), String(total)),
    ),
    h("ul", { class: "u-rows" }, ...detail.rows.map((row) => renderRow(row))),
  );
}
