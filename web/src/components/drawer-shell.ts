/** Static drawer skeleton, its tab strip and the keyboard trap. No task data lives here. */
import type { SendImages } from "@/components/send-images";
import type { TaskDetail } from "@/lib/schemas";

import { askOf } from "@/components/ask-model";
import { iconButton, setIcon } from "@/components/icons";
import { h, must } from "@/lib/dom";

const PANELS = ["activity", "plan", "diff", "live", "checks", "details"] as const;
export type Tab = "questions" | (typeof PANELS)[number];
const TAB_LABEL: Record<Tab, string> = {
  activity: "Activity",
  checks: "Checks",
  details: "Details",
  diff: "Diff",
  live: "Live check",
  plan: "Plan",
  questions: "Questions",
};
const FOCUSABLE = 'button:not([aria-disabled="true"]), textarea, input, select, summary, [href]';
const SLOTS = ["head", "needs", "asks", "actions", "pending", "lesson"];

export interface ShellHandlers {
  onClose: () => void;
  onDetails: () => void;
  onKey: (event: KeyboardEvent) => void;
  onSend: () => void;
}

export function buildShell(feed: HTMLElement, handlers: ShellHandlers, images: SendImages): HTMLElement[] {
  images.box.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) handlers.onSend();
  });
  const panels = PANELS.map((tab) => h("div", { attrs: { "data-panel": tab }, class: "panel" }));
  panels[0]?.append(feed);
  const scroll = h(
    "div",
    { class: "drawer-scroll" },
    ...SLOTS.map((name) => h("div", { attrs: { "data-slot": name } })),
    h("div", { attrs: { "aria-label": "Sections", role: "group" }, class: "dtabs" }),
    h("div", { attrs: { "data-slot": "questions" } }),
    ...panels,
  );
  const bar = h(
    "div",
    { class: "drawer-bar" },
    iconButton("info", "Details", { "aria-expanded": false, "data-details": true, hidden: true }, handlers.onDetails),
    h("span", { attrs: { "data-slot": "mode", hidden: true }, class: "drawer-mode" }),
    iconButton("close", "Close", { "data-close": true }, handlers.onClose),
  );
  const footer = h(
    "footer",
    { attrs: { "data-slot": "send", hidden: true }, class: "drawer-send" },
    images.box,
    h("div", { class: "send-row" }, ...images.nodes, h("div", { attrs: { "data-slot": "send-action" } })),
  );
  const aside = h(
    "aside",
    {
      attrs: { "aria-labelledby": "drawer-title", "aria-modal": "true", role: "dialog", tabindex: -1 },
      class: "drawer",
      on: { keydown: handlers.onKey },
    },
    bar,
    scroll,
    footer,
  );
  return [h("div", { class: "scrim", on: { click: handlers.onClose } }), aside];
}

export function paintTabs(root: HTMLElement, detail: null | TaskDetail, active: Tab, onTab: (tab: Tab) => void): void {
  const ask = detail === null ? null : askOf(detail);
  // Open questions only: answered ones from an earlier turn are history, not a count to clear (T2274).
  const open = ask?.kind === "spec" ? ask.questions.filter((question) => (question.answer ?? "") === "").length : 0;
  const counts: Partial<Record<Tab, number>> = {
    ...(open > 0 && { questions: open }),
    checks: detail?.checks?.results.length ?? 0,
    diff: detail?.diff?.files.length ?? 0,
    live: detail?.live_check?.shots.length ?? 0,
  };
  must(root, ".dtabs").replaceChildren(
    ...(ask === null ? PANELS : (["questions", ...PANELS] as const)).map((tab) => {
      return h("button", {
        attrs: { "aria-pressed": tab === active, "data-tab": tab, type: "button" },
        class: "dtab",
        on: {
          click: () => {
            onTab(tab);
          },
        },
        text: counts[tab] === undefined ? TAB_LABEL[tab] : `${TAB_LABEL[tab]} (${String(counts[tab])})`,
      });
    },
    ),
  );
  for (const panel of root.querySelectorAll<HTMLElement>("[data-panel]")) panel.hidden = panel.dataset.panel !== active;
  must<HTMLElement>(root, '[data-slot="questions"]').hidden = active !== "questions";
  must<HTMLElement>(root, '[data-slot="mode"]').hidden = active !== "questions";
  must(root, ".drawer").classList.toggle("drawer--ask", active === "questions");
}

/** A card that needs answers shows only the questions; one Details toggle brings the tabs and header actions back. */
export function paintFocus(root: HTMLElement, isOnlyAsk: boolean, isOpen: boolean): void {
  const toggle = must<HTMLElement>(root, "[data-details]");
  toggle.hidden = !isOnlyAsk;
  toggle.setAttribute("aria-expanded", String(isOpen));
  setIcon(toggle, "info", isOpen ? "Hide details" : "Details");
  must(root, ".drawer").classList.toggle("drawer--only-ask", isOnlyAsk && !isOpen);
}

/** Keep Tab inside the dialog (aria-modal). */
export function trapTab(event: KeyboardEvent, root: HTMLElement): void {
  const items = [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((item) => !item.closest("[hidden]"));
  const index = items.findIndex((item) => item.matches(":focus"));
  if (index === 0 && event.shiftKey) {
    event.preventDefault();
    items.at(-1)?.focus();
  } else if (index === items.length - 1 && !event.shiftKey) {
    event.preventDefault();
    items[0]?.focus();
  }
}
