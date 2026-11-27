import type { NeedsCategory, Status, TaskCard, TriageLabel } from "@/lib/schemas-common";

/** One board card. Every word comes from the server's card; the status label is display text for the enum only. */
import { icon, type IconName } from "@/components/icons";
import { tileImage } from "@/components/note-images";
import { partsStrip, waitsBadge } from "@/components/repo-parts";
import { badge, umbrellaProgress } from "@/components/umbrella";
import { h } from "@/lib/dom";
import { formatAgo, formatClock, formatIn, formatUsd } from "@/lib/format";

export const STATUS_LABEL: Record<Status, string> = {
  backlog: "Backlog",
  cancelled: "Abandoned",
  done: "Done",
  done_manually: "Done manually",
  needs_you: "Needs you",
  paused_limit: "Paused: plan limit",
  queued: "Queued",
  shipping: "Shipping",
  waiting_phone_update: "Waiting for phone",
  working: "Working",
  yours: "Yours",
};

export const STATUS_TONE: Record<Status, "accent" | "muted" | "ok" | "warn"> = {
  backlog: "muted",
  cancelled: "muted",
  done: "muted",
  done_manually: "muted",
  needs_you: "warn",
  paused_limit: "warn",
  queued: "muted",
  shipping: "accent",
  waiting_phone_update: "accent",
  working: "accent",
  yours: "muted",
};

export function statusChip(status: Status): HTMLElement {
  return h("span", { attrs: { "data-tone": STATUS_TONE[status] }, class: "chip", text: STATUS_LABEL[status] });
}

/** "free credits" badge: only when the server says the latest turn ran on free API credits. */
export function routeChip(card: TaskCard): false | HTMLElement {
  return card.route === "credits" && h("span", { attrs: { "data-tone": "accent" }, class: "chip route-chip", text: "free credits" });
}

const TIER_ORDER = ["cheap", "free", "escalated"] as const satisfies readonly IconName[];
const TIER_LABEL: Record<(typeof TIER_ORDER)[number], string> = { cheap: "Cheap", escalated: "Escalated", free: "Free models" };

/** Icon-only cheap-tier badges (cheap, free models, escalated): the flags are the server's, the order is fixed. */
export function tierBadges(card: TaskCard): HTMLElement[] {
  return TIER_ORDER.filter((name) => card.tier[name]).map((name) =>
    h("span", { attrs: { "aria-label": TIER_LABEL[name], "data-tier": name, role: "img", title: TIER_LABEL[name] }, class: "tier-badge" }, icon(name)),
  );
}

const TRIAGE_ICON = { all_repos: "all", existing_repo: "folder", manual: "person", new_repo: "plus", research: "search" } as const satisfies Record<TriageLabel, IconName>;
const TRIAGE_NAME: Record<TriageLabel, string> = { all_repos: "All repos", existing_repo: "Existing repo", manual: "Yours", new_repo: "New repo", research: "Research" };

/** Icon-only triage label of a card that had no repo: the label is the server's, the words are tooltip and aria-label only. */
export function triageBadge(card: TaskCard): HTMLElement[] {
  const label = card.triage;
  return label === undefined ? [] : [h("span", { attrs: { "aria-label": TRIAGE_NAME[label], "data-triage": label, role: "img", title: TRIAGE_NAME[label] }, class: "tier-badge" }, icon(TRIAGE_ICON[label]))];
}

const CATEGORY_LABEL: Record<NeedsCategory, string> = {
  action: "Action",
  auto: "Fixing itself",
  criteria: "Criteria",
  permission: "Permission",
  phone: "Phone",
  questions: "Questions",
};

/** "auto: done_check passed at 14:05" on a run a passing done_check started; the time is the server's. */
export function autoBadge(card: TaskCard): null | string {
  return card.auto_start === null ? null : `auto: done_check passed at ${formatClock(card.auto_start.passed_at)}`;
}

/** "partial: 3/5, follow-up abcd1234 · after ship: C7, C14"; every list comes from the server. */
export function partialLine(partial: NonNullable<TaskCard["partial"]>): string {
  const total = partial.done.length + partial.open.length;
  const followup = partial.followup_id === null ? "" : `, follow-up ${partial.followup_id}`;
  const parts = [
    partial.open.length > 0 && `partial: ${String(partial.done.length)}/${String(total)}${followup}`,
    partial.deferred.length > 0 && `after ship: ${partial.deferred.join(", ")}`,
  ].filter((part): part is string => part !== false);
  return parts.join(" · ");
}

function resumeLine(card: TaskCard, now: number): null | string {
  return card.resumes_at === null ? null : `resumes ${formatIn(card.resumes_at, now)} (${formatClock(card.resumes_at)})`;
}

/** The server's line on what the card does; a card that ships itself gets a spinner before it (T2060). */
function currentLine(card: TaskCard): HTMLElement {
  const spinner = card.status === "shipping" && h("span", { attrs: { "aria-hidden": "true" }, class: "spinner" });
  return h("span", { attrs: { "data-shipping": String(card.status === "shipping") }, class: "card-current" }, spinner, card.current);
}

export function renderCard(card: TaskCard, now: number, shouldShowRepo = false): HTMLButtonElement {
  const resume = resumeLine(card, now);
  const meta = [
    shouldShowRepo ? (card.repo ?? "Yours") : null,
    `#${card.id}`,
    card.cost_usd > 0 ? formatUsd(card.cost_usd) : null,
    formatAgo(card.updated, now),
  ].filter((part): part is string => part !== null);
  return h(
    "button",
    { attrs: { "data-id": card.id, "data-status": card.status, type: "button" }, class: "card" },
    h(
      "span",
      { class: "card-top" },
      statusChip(card.status),
      routeChip(card),
      ...tierBadges(card),
      ...triageBadge(card),
      card.app_error !== undefined && badge("issue", "App error", card.app_error, { "data-app-error": "" }),
      h("span", { class: "card-prio", text: card.priority }),
    ),
    h("span", { class: "card-title", text: card.title }),
    tileImage(card),
    currentLine(card),
    resume !== null && h("span", { class: "card-current", text: resume }),
    card.umbrella !== undefined && umbrellaProgress(card.umbrella),
    card.parts !== undefined && card.parts.length > 0 && partsStrip(card.parts),
    card.waits_on != null && waitsBadge(card.waits_on),
    card.needs !== null && card.needs.text !== card.current && h("span", { class: "card-needs", text: card.needs.text }),
    card.needs !== null && h("span", { attrs: { "data-category": card.needs.category }, class: "card-category", text: CATEGORY_LABEL[card.needs.category] }),
    card.partial !== null && h("span", { class: "card-partial", text: partialLine(card.partial) }),
    card.auto !== null && h("span", { class: "card-auto", text: `auto: ${card.auto}` }),
    card.auto_start !== null && h("span", { attrs: { "data-tone": "accent" }, class: "chip card-badge", text: autoBadge(card) ?? "" }),
    h("span", { class: "card-meta", text: meta.join(" · ") }),
  );
}
