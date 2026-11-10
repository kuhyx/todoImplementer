import type { Board, Usage } from "@/lib/schemas";

/** 5 h / 7 d plan windows, today's dollars, running count and any active limit. All numbers come from /api/usage and /api/board. */
import { renderCreditsToggle } from "@/components/credits-toggle";
import { renderFree } from "@/components/free-strip";
import { h } from "@/lib/dom";
import { formatClock, formatIn, formatPercent, formatUsd } from "@/lib/format";

const noop = (): void => undefined;
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
  return h("p", { attrs: { role: "status" }, class: "limit-note", text: `Plan limit reached: runs resume ${until}. ${board.limit.credits.text}` });
}

/** The API key banner: the server words it (`api_key.text`); red alert for errors, amber status for a warning. */
function keyBanner(board: Board | null): HTMLElement | null {
  const key = board?.api_key;
  if (!key || key.level === "ok") return null;
  return h("p", {
    attrs: { "data-level": key.level, "data-state": key.state, role: key.level === "error" ? "alert" : "status" },
    class: "banner key-banner",
    text: key.text,
  });
}

/** Red banner while the overage guard's alert is on; the server words it (`alert.text`). */
function overageAlert(board: Board | null): HTMLElement | null {
  const alert = board?.alert;
  return alert ? h("p", { attrs: { "data-kind": alert.kind, role: "alert" }, class: "banner alert-banner", text: alert.text }) : null;
}

/** `onCredits` runs after the credits toggle's POST settles (the app refreshes the board). */
export function renderUsage(usage: null | Usage, board: Board | null, error: null | string, build: null | string, now: number, onCredits: () => void = noop): HTMLElement {
  return h(
    "div",
    { class: "usage" },
    h("div", { class: "usage-row" },
      h("h1", { class: "brand", text: "todoImplementer" }),
      build !== null && h("span", { class: "build", text: build }),
      board !== null && h("span", { class: "slots", text: `Running ${String(board.slots.used)}` }),
      board !== null && h("span", { class: "auto-close", text: `auto close: ${board.auto_close ? "on" : "off"}` }),
      usage !== null && h("span", { class: "today", text: `Today ${formatUsd(usage.cost.today_usd)}` }),
      h("a", { attrs: { href: "/usage" }, class: "usage-link", text: "Usage details" }),
      usage !== null && usage.overage.using && h("span", { attrs: { "data-tone": "warn" }, class: "chip", text: "Overage in use" }),
    ),
    usage !== null && h("div", { class: "usage-row" }, meter("5 h", usage.five_hour, now), meter("7 d", usage.seven_day, now), renderFree(usage.free, now)),
    error !== null && h("p", { attrs: { role: "alert" }, class: "banner", text: error }),
    keyBanner(board),
    overageAlert(board),
    board !== null && renderCreditsToggle(board.limit.credits, onCredits),
    limitNote(board, now),
  );
}
