import type { NeedsCategory, Status, TaskCard } from "@/lib/schemas-common";

/** One board card. Every word comes from the server's card; the status label is display text for the enum only. */
import { h } from "@/lib/dom";
import { formatAgo, formatClock, formatIn, formatUsd } from "@/lib/format";

export const STATUS_LABEL: Record<Status, string> = {
  backlog: "Backlog",
  cancelled: "Cancelled",
  done: "Done",
  needs_you: "Needs you",
  paused_limit: "Paused: plan limit",
  queued: "Queued",
  ready_to_ship: "Ready to ship",
  shipping: "Shipping",
  working: "Working",
  yours: "Yours",
};

export const STATUS_TONE: Record<Status, "accent" | "muted" | "ok" | "warn"> = {
  backlog: "muted",
  cancelled: "muted",
  done: "muted",
  needs_you: "warn",
  paused_limit: "warn",
  queued: "muted",
  ready_to_ship: "ok",
  shipping: "accent",
  working: "accent",
  yours: "muted",
};

export function statusChip(status: Status): HTMLElement {
  return h("span", { attrs: { "data-tone": STATUS_TONE[status] }, class: "chip", text: STATUS_LABEL[status] });
}

const CATEGORY_LABEL: Record<NeedsCategory, string> = {
  action: "Action",
  auto: "Fixing itself",
  criteria: "Criteria",
  permission: "Permission",
  phone: "Phone",
  questions: "Questions",
};

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

export function renderCard(card: TaskCard, now: number): HTMLButtonElement {
  const resume = resumeLine(card, now);
  const meta = [
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
      h("span", { class: "card-prio", text: card.priority }),
    ),
    h("span", { class: "card-title", text: card.title }),
    h("span", { class: "card-current", text: card.current }),
    resume !== null && h("span", { class: "card-current", text: resume }),
    card.needs !== null && h("span", { class: "card-needs", text: card.needs.text }),
    card.needs !== null && h("span", { attrs: { "data-category": card.needs.category }, class: "card-category", text: CATEGORY_LABEL[card.needs.category] }),
    card.partial !== null && h("span", { class: "card-partial", text: partialLine(card.partial) }),
    h("span", { class: "card-meta", text: meta.join(" · ") }),
  );
}
