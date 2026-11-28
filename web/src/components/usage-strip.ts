import type { Board, Usage } from "@/lib/schemas";

/** The one-row top bar: build name, the 7 d plan window, free models left/used, the no-limit runner, the paced credits, usage and sessions links; then banners. Numbers come from /api/usage and /api/board. */
import { renderCreditsPace } from "@/components/credits-pace";
import { renderFree } from "@/components/free-strip";
import { icon } from "@/components/icons";
import { renderNoLimit } from "@/components/nolimit-strip";
import { h } from "@/lib/dom";
import { formatClock, formatIn, formatPercent } from "@/lib/format";

/** Icon link to the page of sessions kuhy started by hand; its name lives in `title` and `aria-label` (textgate). */
function sessionsLink(): HTMLElement {
  const link = h("a", { attrs: { "aria-label": "Manual sessions", href: "/sessions", title: "Manual sessions" }, class: "btn icon-btn sessions-link" });
  link.append(icon("terminal"));
  return link;
}
type Window = Usage["five_hour"];

function tone(utilization: number): string {
  if (utilization >= 0.9) return "danger";
  return utilization >= 0.75 ? "warn" : "ok";
}

const RESERVE = [
  { at: 90, lit: ["low_medium", "all"] },
  { at: 95, lit: ["all"] },
] as const;

/** The weekly reserve (T2533): a tick at 90 % and 95 % of the 7 d window, lit while that hold is on. */
function reserveTicks(hold: string): HTMLElement[] {
  return RESERVE.map(({ at, lit }) => {
    const isLit = (lit as readonly string[]).includes(hold);
    const tick = h("span", { attrs: { "data-at": at, "data-lit": String(isLit), title: isLit ? "Reserve" : undefined }, class: "r-tick" });
    tick.style.setProperty("--at", `${String(at)}%`);
    return tick;
  });
}

/** The daily allowance: a tick where day N of 7 ends (N/7), lit while it holds the board. */
function allowanceTick(allowance: null | number, hold: string): HTMLElement[] {
  if (allowance === null) return [];
  const tick = h("span", { attrs: { "data-lit": String(hold === "allowance") }, class: "a-tick" });
  tick.style.setProperty("--at", `${String(Math.round(allowance * 100))}%`);
  return [tick];
}

function meter(label: string, window: Window, now: number, hold = "none", allowance: null | number = null): HTMLElement {
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
      ...(label === "7 d" ? [...reserveTicks(hold), ...allowanceTick(allowance, hold)] : []),
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

/** Red banner while an alert is on (overage guard, or the phone relay failing closed); the server words it. */
function overageAlert(board: Board | null): HTMLElement | null {
  const alert = board?.alert;
  return alert ? h("p", { attrs: { "data-kind": alert.kind, role: "alert" }, class: "banner alert-banner", text: alert.text }) : null;
}

export function renderUsage(usage: null | Usage, board: Board | null, error: null | string, build: null | string, now: number): HTMLElement {
  return h(
    "div",
    { class: "usage" },
    h("div", { class: "usage-row" },
      build !== null && h("span", { class: "build", text: build }),
      usage !== null && meter("7 d", usage.seven_day, now, board?.limit.weekly_hold, board?.limit.weekly_allowance),
      board?.limit.weekly_hold === "allowance" && h("span", { attrs: { "data-tone": "warn" }, class: "chip", text: `held: allowance ${String(Math.round((board.limit.weekly_allowance ?? 0) * 100))}%` }),
      usage !== null && renderFree(usage.free, now),
      usage !== null && renderNoLimit(usage.nolimit, now),
      board !== null && renderCreditsPace(board.limit.credits),
      h("a", { attrs: { href: "/usage" }, class: "usage-link", text: "Usage details" }),
      sessionsLink(),
      usage !== null && usage.overage.using && h("span", { attrs: { "data-tone": "warn" }, class: "chip", text: "Overage in use" }),
    ),
    error !== null && h("p", { attrs: { role: "alert" }, class: "banner", text: error }),
    keyBanner(board),
    overageAlert(board),
    limitNote(board, now),
  );
}
