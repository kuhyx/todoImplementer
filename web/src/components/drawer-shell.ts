import type { TaskDetail } from "@/lib/schemas";

/** Static drawer skeleton, its tab strip and the keyboard trap. No task data lives here. */
import { h, must } from "@/lib/dom";

export const TABS = ["activity", "plan", "diff", "live", "checks", "details"] as const;
export type Tab = (typeof TABS)[number];
const TAB_LABEL: Record<Tab, string> = {
  activity: "Activity",
  checks: "Checks",
  details: "Details",
  diff: "Diff",
  live: "Live check",
  plan: "Plan",
};
const FOCUSABLE = 'button:not([aria-disabled="true"]), textarea, input, select, summary, [href]';
const SLOTS = ["head", "needs", "actions", "pending", "questions", "lesson"];

export interface ShellHandlers {
  onClose: () => void;
  onKey: (event: KeyboardEvent) => void;
  onSend: () => void;
}

export function buildShell(feed: HTMLElement, handlers: ShellHandlers): HTMLElement[] {
  const send = h("textarea", {
    attrs: {
      "aria-label": "Message to Claude",
      "data-keep": true,
      name: "send",
      placeholder: "Send to Claude: a note, an answer or a correction",
      rows: 2,
    },
    on: {
      keydown: (event) => {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) handlers.onSend();
      },
    },
  });
  const panels = TABS.map((tab) => h("div", { attrs: { "data-panel": tab }, class: "panel" }));
  panels[0]?.append(feed);
  const scroll = h(
    "div",
    { class: "drawer-scroll" },
    ...SLOTS.map((name) => h("div", { attrs: { "data-slot": name } })),
    h("div", { attrs: { "aria-label": "Sections", role: "group" }, class: "dtabs" }),
    ...panels,
  );
  const bar = h(
    "div",
    { class: "drawer-bar" },
    h("button", { attrs: { type: "button" }, class: "btn", on: { click: handlers.onClose }, text: "Close" }),
  );
  const footer = h(
    "footer",
    { attrs: { "data-slot": "send", hidden: true }, class: "drawer-send" },
    send,
    h("div", { attrs: { "data-slot": "send-action" } }),
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
  const counts: Partial<Record<Tab, number>> = {
    checks: detail?.checks?.results.length ?? 0,
    diff: detail?.diff?.files.length ?? 0,
    live: detail?.live_check?.shots.length ?? 0,
  };
  must(root, ".dtabs").replaceChildren(
    ...TABS.map((tab) => {
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
