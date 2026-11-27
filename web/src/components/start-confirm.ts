import type { ActionWaits } from "@/lib/schemas-common";

/**
 * Start while a higher-priority card waits in Backlog (T2583): a modal names that card (its priority glyph and
 * title) and asks "Start anyway?". kuhy asked for the question, so it is the one line of text. Resolves true
 * on Start anyway, false on Back, Escape or a click outside. The dialog lives on <body>, so the drawer's own
 * Escape and Tab handling never sees its keys.
 */
import { icon } from "@/components/icons";
import { priorityGlyph } from "@/components/priority-picker";
import { h } from "@/lib/dom";

export async function isStartConfirmed(waits: ActionWaits): Promise<boolean> {
  return await new Promise<boolean>((resolve) => {
    const finish = (isStarting: boolean): void => {
      dialog.close();
      dialog.remove();
      resolve(isStarting);
    };
    const back = h("button", { attrs: { "data-start-confirm": "back", type: "button" }, class: "btn", on: { click: () => { finish(false); } }, text: "Back" });
    const go = h("button", { attrs: { "data-start-confirm": "go", type: "button" }, class: "btn primary", on: { click: () => { finish(true); } }, text: "Start anyway" });
    const waiting = h(
      "p",
      { attrs: { "data-waits": waits.id, title: waits.priority }, class: "start-confirm-waits" },
      icon(priorityGlyph(waits.priority)),
      h("span", { text: waits.title }),
    );
    const dialog = h(
      "dialog",
      { attrs: { "aria-labelledby": "start-confirm-title", "data-start-confirm": "" }, class: "start-confirm" },
      h("h2", { attrs: { id: "start-confirm-title" }, text: "Start anyway?" }),
      waiting,
      h("div", { class: "start-confirm-row" }, back, go),
    );
    dialog.addEventListener("keydown", (event) => { event.stopPropagation(); });
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      finish(false);
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) finish(false);
    });
    document.body.append(dialog);
    dialog.showModal();
    go.focus();
  });
}
