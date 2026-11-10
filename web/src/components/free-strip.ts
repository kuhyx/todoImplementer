import type { Free } from "@/lib/schemas-free";

/** The free-model gateway as a compact strip of icons and numbers. Words live only in title and aria-label. */
import { icon, type IconName } from "@/components/icons";
import { h } from "@/lib/dom";
import { formatAgo, formatClock, formatCompact } from "@/lib/format";

type Quota = Free["quotas"][number];
type Step = NonNullable<Free["combo"]>["steps"][number];
type Tone = "danger" | "ok" | "unknown" | "warn";

const GATEWAY_TONE: Record<Free["state"], Tone> = { down: "danger", ok: "ok", stale: "warn", unknown: "unknown" };
const STATE_LABEL: Record<Free["state"], string> = { down: "unreachable, last reading shown", ok: "ok", stale: "old reading", unknown: "not read yet" };

function chip(name: IconName, label: string, value?: string, attributes: Record<string, string> = {}): HTMLElement {
  return h(
    "span",
    { attrs: { "aria-label": label, role: "img", title: label, ...attributes }, class: "f-chip" },
    icon(name),
    value !== undefined && h("span", { class: "f-num", text: value }),
  );
}

function quotaTone(left: number): Tone {
  if (left < 10) return "danger";
  return left < 30 ? "warn" : "ok";
}

function quotaMeter(quota: Quota): HTMLElement {
  const left = Math.round(quota.left_pct);
  const reset = quota.reset_at === null ? "" : `, resets ${formatClock(quota.reset_at)}`;
  const label = `${quota.provider} ${quota.label}: ${String(quota.total - quota.used)} of ${String(quota.total)} left${reset}`;
  const fill = h("span", { class: "f-meter-fill" });
  fill.style.setProperty("--fill", `${String(left)}%`);
  return h(
    "span",
    { attrs: { "aria-label": label, "aria-valuemax": 100, "aria-valuemin": 0, "aria-valuenow": left, "data-tone": quotaTone(quota.left_pct), role: "meter", title: label }, class: "f-meter" },
    fill,
  );
}

function stepDot(step: Step): HTMLElement {
  const rate = step.ok_pct === null ? "no calls" : `${String(Math.round(step.ok_pct))}%`;
  const label = `${step.provider} ${step.model} ${rate}, ${String(step.requests)} requests (${step.state})`;
  return h("span", { attrs: { "aria-label": label, "data-state": step.state, role: "img", title: label }, class: "f-dot" });
}

function providerChips(free: Free): HTMLElement[] {
  const named = (state: string): string => free.providers.filter((p) => p.state === state).map((p) => p.id).join(", ");
  const cooling = free.providers
    .filter((p) => p.state === "cooling")
    .map((p) => (p.until === null ? p.id : `${p.id} until ${formatClock(p.until)}`))
    .join(", ");
  const failing = [named("failing"), named("off")].filter((text) => text !== "").join(", ");
  return [
    chip("check", `Providers answering: ${String(free.counts.ok)} of ${String(free.counts.providers)}`, String(free.counts.ok), { "data-kind": "ok" }),
    free.counts.cooling > 0 && chip("cooling", `Cooling down: ${cooling}`, String(free.counts.cooling), { "data-kind": "cooling" }),
    free.counts.failing > 0 && chip("failed", `Failing or off: ${failing}`, String(free.counts.failing), { "data-kind": "failing" }),
  ].filter((node): node is HTMLElement => node !== false);
}

function tokenChips(free: Free): HTMLElement[] {
  const { tokens } = free;
  if (tokens === null) return [];
  const total = tokens.in + tokens.out;
  const wide = `${String(tokens.in)} in, ${String(tokens.out)} out, ${String(tokens.requests)} requests`;
  return [
    chip("tokens", `Tokens today, every client of the gateway: ${wide}`, formatCompact(total), { "data-kind": "tokens" }),
    ...(tokens.ours === null ? [] : [chip("free", `Tokens today of our free workers: ${String(tokens.ours)}`, formatCompact(tokens.ours), { "data-kind": "ours" })]),
  ];
}

/** One strip: gateway state, providers, quotas, tokens today, the combo chain. Unread or absent: the grey gateway icon alone. */
export function renderFree(free: Free | undefined, now: number): HTMLElement {
  const state = free?.state ?? "unknown";
  const age = free?.at == null ? "" : `, read ${formatAgo(free.at, now)}`;
  const error = free?.error == null ? "" : ` (${free.error})`;
  const gateway = chip("gateway", `Free-model gateway: ${STATE_LABEL[state]}${age}${error}`, undefined, { "data-kind": "gateway", "data-tone": GATEWAY_TONE[state] });
  const shown = free !== undefined && state !== "unknown" ? free : undefined;
  return h(
    "div",
    { attrs: { "aria-label": "Free models", "data-state": state, role: "group" }, class: "free-strip" },
    gateway,
    shown && h("span", { class: "f-group" }, ...providerChips(shown)),
    shown && shown.quotas.length > 0 && h("span", { class: "f-group" }, ...shown.quotas.map((quota) => quotaMeter(quota))),
    shown && h("span", { class: "f-group" }, ...tokenChips(shown)),
    shown?.combo != null && h("span", { attrs: { "aria-label": `Chain ${shown.combo.name}`, role: "group" }, class: "f-chain" }, ...shown.combo.steps.map((step) => stepDot(step))),
    shown && shown.models.cooling > 0 && chip("cooling", `Models cooling down: ${String(shown.models.cooling)} of ${String(shown.models.total)}`, String(shown.models.cooling), { "data-kind": "models" }),
  );
}
