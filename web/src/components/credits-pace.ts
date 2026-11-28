import type { Credits } from "@/lib/schemas-common";

/**
 * The paced free credits as one bar and numbers: spent this period against the monthly grant, a tick at each of
 * the four weekly caps and the current one lit. The server computes every figure (`limit.credits`); "≈" marks the
 * ones that are estimates of the Console bill. Words live only in the tooltip (textgate).
 */
import { icon, iconButton } from "@/components/icons";
import { csrfToken } from "@/lib/boot";
import { h } from "@/lib/dom";
import { formatUsd } from "@/lib/format";
import { postCreditsFallback } from "@/lib/http";

const WEEKS = [1, 2, 3, 4] as const;

type Tone = "danger" | "ok" | "warn";

function tone(credits: Credits): Tone {
  if (credits.over_cap) return "danger";
  return credits.spent_period_usd >= credits.cap_usd * 0.8 ? "warn" : "ok";
}

function tooltip(credits: Credits): string {
  const next = credits.route ?? "waits";
  return [
    `Spent this period (estimate, SDK cost x ${String(credits.cost_factor)}): ${formatUsd(credits.spent_period_usd)}`,
    `cap this week (${String(credits.week)} of 4): ${formatUsd(credits.cap_usd)}`,
    `monthly grant: ${formatUsd(credits.monthly_usd)}`,
    `remaining: ${formatUsd(credits.remaining_usd)}`,
    `credit turns: ${String(credits.credit_turns_period)}, running: ${String(credits.running_credit_turns)}`,
    `next turn: ${next}`,
    `batches pending: ${String(credits.batches.pending)}`,
  ].join("; ");
}

function bar(credits: Credits): HTMLElement {
  const share = (usd: number): number => (credits.monthly_usd > 0 ? Math.min(100, (usd / credits.monthly_usd) * 100) : 0);
  const fill = h("span", { class: "c-fill" });
  fill.style.setProperty("--fill", `${String(share(credits.spent_period_usd))}%`);
  const ticks = WEEKS.map((week) => {
    const tick = h("span", { attrs: { "data-current": String(week === credits.week), "data-week": week }, class: "c-tick" });
    tick.style.setProperty("--at", `${String(share((week * credits.monthly_usd) / WEEKS.length))}%`);
    return tick;
  });
  return h(
    "span",
    { attrs: { "aria-valuemax": credits.monthly_usd, "aria-valuemin": 0, "aria-valuenow": credits.spent_period_usd, role: "meter" }, class: "c-bar" },
    fill,
    ...ticks,
  );
}

/** Pending one-shots on the Batches API (T2532): a spinner, their count, the oldest's age in the tooltip. */
function batches(credits: Credits, now: number): HTMLElement | null {
  const { oldest_at: oldest, pending } = credits.batches;
  if (pending === 0) return null;
  const age = oldest === null ? 0 : Math.max(0, Math.floor((now - oldest) / 60));
  const label = `Batch: ${String(pending)} pending, oldest ${String(age)} min`;
  return h(
    "span",
    { attrs: { "aria-label": label, "data-pending": pending, role: "status", title: label }, class: "c-batch" },
    h("span", { attrs: { "aria-hidden": "true" }, class: "spinner" }),
    h("span", { class: "c-num", text: String(pending) }),
  );
}

/**
 * The board switches the credits off by itself when the balance is gone (`off_text`, worded by the server); this
 * button is the only way back on (POST /api/settings/credits-fallback). It shows whenever the credits are off.
 */
function switchOn(credits: Credits): HTMLElement[] {
  if (credits.enabled) return [];
  const turnOn = async (button: HTMLElement): Promise<void> => {
    const csrf = csrfToken();
    if (csrf === null) return;
    button.setAttribute("aria-disabled", "true");
    try {
      await postCreditsFallback(true, csrf);
      button.dispatchEvent(new CustomEvent("credits-changed", { bubbles: true }));
    } catch {
      button.removeAttribute("aria-disabled");
    }
  };
  const button = iconButton("running", "Turn credits on", {}, () => {
    void turnOn(button);
  });
  return [
    ...(credits.off_text === null ? [] : [h("span", { attrs: { "data-tone": "danger", role: "status" }, class: "chip c-off", text: credits.off_text })]),
    button,
  ];
}

export function renderCreditsPace(credits: Credits, now: number = Date.now() / 1000): HTMLElement {
  const label = tooltip(credits);
  return h(
    "span",
    { attrs: { "aria-label": label, "data-route": credits.route ?? "wait", "data-tone": tone(credits), role: "group", title: label }, class: "credits-pace" },
    icon("free"),
    bar(credits),
    h("span", { class: "c-num", text: `≈${formatUsd(credits.spent_period_usd)} / ${formatUsd(credits.cap_usd)}` }),
    h("span", { class: "c-num c-left", text: `≈${formatUsd(credits.remaining_usd)}` }),
    batches(credits, now),
    ...switchOn(credits),
  );
}
