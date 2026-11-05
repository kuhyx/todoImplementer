import type { Board, Usage } from "@/lib/schemas";

/** 5 h / 7 d plan windows, today's dollars, running count and any active limit. All numbers come from /api/usage and /api/board. */
import { h } from "@/lib/dom";
import { formatClock, formatIn, formatPercent, formatUsd } from "@/lib/format";

type Window = Usage["five_hour"];

function tone(utilization: number): string {
  if (utilization >= 0.9) return "danger";
  return utilization >= 0.75 ? "warn" : "ok";
}

function meter(label: string, window: Window, now: number): HTMLElement {
  if (window === null) {
    return h("div", { class: "meter-box" }, h("span", { class: "meter-label", text: label }), h("span", { class: "meter-note", text: "no reading yet" }));
  }
  const fill = h("span", { class: "meter-fill" });
  fill.style.setProperty("--fill", `${String(Math.min(100, Math.round(window.utilization * 100)))}%`);
  return h(
    "div",
    { attrs: { "data-tone": tone(window.utilization) }, class: "meter-box" },
    h("span", { class: "meter-label", text: label }),
    h(
      "span",
      { attrs: { "aria-label": `${label} used`, "aria-valuemax": 100, "aria-valuemin": 0, "aria-valuenow": Math.round(window.utilization * 100), role: "meter" }, class: "meter" },
      fill,
    ),
    h("span", { class: "meter-value", text: formatPercent(window.utilization) }),
    h("span", { class: "meter-note", text: `resets ${formatIn(window.resets_at, now)} (${formatClock(window.resets_at)})` }),
  );
}

function limitNote(board: Board | null, now: number): HTMLElement | null {
  if (!board?.limit.active) return null;
  const until = board.limit.until === null ? "at an unknown time" : `${formatIn(board.limit.until, now)} (${formatClock(board.limit.until)})`;
  const credits = board.limit.credits_available ? "Run on credits is available per task." : "Credits are not available.";
  return h("p", { attrs: { role: "status" }, class: "limit-note", text: `Plan limit reached: runs resume ${until}. ${credits}` });
}

export function renderUsage(usage: null | Usage, board: Board | null, error: null | string, build: null | string, now: number): HTMLElement {
  return h(
    "div",
    { class: "usage" },
    h("div", { class: "usage-row" },
      h("h1", { class: "brand", text: "todoImplementer" }),
      build !== null && h("span", { class: "build", text: build }),
      board !== null && h("span", { class: "slots", text: `Running ${String(board.slots.used)}` }),
      usage !== null && h("span", { class: "today", text: `Today ${formatUsd(usage.cost.today_usd)}` }),
      h("a", { attrs: { href: "/usage" }, class: "usage-link", text: "Usage details" }),
      usage !== null && usage.overage.using && h("span", { attrs: { "data-tone": "warn" }, class: "chip", text: "Using credits" }),
    ),
    usage !== null && h("div", { class: "usage-row" }, meter("5 h", usage.five_hour, now), meter("7 d", usage.seven_day, now)),
    error !== null && h("p", { attrs: { role: "alert" }, class: "banner", text: error }),
    limitNote(board, now),
  );
}
