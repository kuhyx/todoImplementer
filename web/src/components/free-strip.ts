import type { Free } from "@/lib/schemas-free";

/**
 * The free models in two numbers (kuhy, 2026-11-20: "just how many we still have left and how many we used"): what
 * the providers' free quotas still allow (their units, requests per window, summed) and the tokens our free workers
 * used today (every client's when the gateway does not split ours out). Words live only in title and aria-label.
 */
import { icon, type IconName } from "@/components/icons";
import { h } from "@/lib/dom";
import { formatAgo, formatCompact } from "@/lib/format";

const STATE_LABEL: Record<Free["state"], string> = { down: "unreachable, last reading shown", ok: "ok", stale: "old reading", unknown: "not read yet" };

function chip(kind: string, name: IconName, label: string, value: null | number): HTMLElement {
  return h(
    "span",
    { attrs: { "aria-label": label, "data-kind": kind, role: "img", title: label }, class: "f-chip" },
    icon(name),
    h("span", { class: "f-num", text: value === null ? "-" : formatCompact(value) }),
  );
}

function left(free: Free | undefined): null | number {
  const quotas = free?.quotas ?? [];
  return quotas.length === 0 ? null : quotas.reduce((sum, quota) => sum + Math.max(0, quota.total - quota.used), 0);
}

function used(free: Free | undefined): null | number {
  const tokens = free?.tokens ?? null;
  return tokens === null ? null : (tokens.ours ?? tokens.in + tokens.out);
}

export function renderFree(free: Free | undefined, now: number): HTMLElement {
  const state = free?.state ?? "unknown";
  const age = free?.at == null ? "" : `, read ${formatAgo(free.at, now)}`;
  const gateway = ` (gateway ${STATE_LABEL[state]}${age})`;
  return h(
    "div",
    { attrs: { "aria-label": "Free models", "data-state": state, role: "group" }, class: "free-strip" },
    chip("left", "free", `Free quota left (requests, summed over providers)${gateway}`, left(free)),
    chip("used", "tokens", `Free tokens used today${gateway}`, used(free)),
  );
}
