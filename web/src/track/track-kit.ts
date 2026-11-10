/** Shared pieces of the tracking view: duration text, the icon for each stage and resting reason, one icon+text stat. */
import type { Resting, TrackKid } from "@/lib/schemas-track";

import { icon, type IconName } from "@/components/icons";
import { h } from "@/lib/dom";

/** "45s", "12m", "1h 30m", "2d 3h"; null (nothing measured yet) is a dash. */
export function formatSpan(seconds: null | number): string {
  if (seconds === null) return "–";
  const total = Math.round(seconds);
  if (total < 60) return `${String(total)}s`;
  const minutes = Math.floor(total / 60);
  if (minutes < 60) return `${String(minutes)}m`;
  const hours = Math.floor(minutes / 60);
  return hours < 48 ? `${String(hours)}h ${String(minutes % 60)}m` : `${String(Math.floor(hours / 24))}d ${String(hours % 24)}h`;
}

/** Whole minutes until `until`, rounded up, never negative. */
export function minutesUntil(until: number, now: number): number {
  return Math.max(0, Math.ceil((until - now) / 60));
}

export const RESTING_ICON: Record<Resting["kind"], IconName> = {
  crash: "killed",
  gateway: "gateway",
  killed: "killed",
  limit: "hourglass",
  network: "offline",
  todo: "queued",
  turn: "retry",
};

export const RESTING_LABEL: Record<Resting["kind"], string> = {
  crash: "Waiting to retry after a crash",
  gateway: "Waiting for the free-model gateway",
  killed: "Waiting to retry after a turn was killed",
  limit: "Waiting for the plan usage limit",
  network: "Waiting for the network",
  todo: "Waiting for the todo app",
  turn: "Waiting to retry a failed turn",
};

export const STAGE_ICON: Record<NonNullable<TrackKid["stage"]>, IconName> = {
  cancelled: "close",
  checks: "ready",
  closed: "check",
  closing: "log",
  failed: "failed",
  gate: "ready",
  implement: "running",
  live_check: "running",
  paused_limit: "hourglass",
  paused_retry: "retry",
  plan: "info",
  shipped: "check",
  shipping: "merge",
  spec: "info",
  spec_wait: "queued",
};

/** One icon with a short text (a number or a duration); the name is the accessible label and the tooltip. */
export function stat(name: IconName, label: string, text?: number | string, attributes: Record<string, string> = {}): HTMLElement {
  const full = text === undefined ? label : `${label} ${String(text)}`;
  return h(
    "span",
    { attrs: { "aria-label": full, role: "img", title: full, ...attributes }, class: "t-stat" },
    icon(name),
    text !== undefined && h("span", { class: "t-num", text: String(text) }),
  );
}

/** The resting reason as a stat: its icon and the minutes until the next try. */
export function restingStat(resting: Resting, now: number): HTMLElement {
  const minutes = resting.until === null ? undefined : `${String(minutesUntil(resting.until, now))}m`;
  return stat(RESTING_ICON[resting.kind], RESTING_LABEL[resting.kind], minutes, { "data-resting": resting.kind });
}
