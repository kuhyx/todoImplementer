import type { Credits } from "@/lib/schemas-common";

/**
 * The paced free credits as one bar and numbers: spent this period against the monthly grant, a tick at each of
 * the four weekly caps and the current one lit. The server computes every figure (`limit.credits`); "≈" marks the
 * ones that are estimates of the Console bill. Words live only in the tooltip (textgate).
 */
import { icon } from "@/components/icons";
import { h } from "@/lib/dom";
import { formatUsd } from "@/lib/format";

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

export function renderCreditsPace(credits: Credits): HTMLElement {
  const label = tooltip(credits);
  return h(
    "span",
    { attrs: { "aria-label": label, "data-route": credits.route ?? "wait", "data-tone": tone(credits), role: "group", title: label }, class: "credits-pace" },
    icon("free"),
    bar(credits),
    h("span", { class: "c-num", text: `≈${formatUsd(credits.spent_period_usd)} / ${formatUsd(credits.cap_usd)}` }),
    h("span", { class: "c-num c-left", text: `≈${formatUsd(credits.remaining_usd)}` }),
  );
}
