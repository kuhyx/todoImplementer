import type { Action } from "@/lib/schemas-common";

/**
 * Buttons come only from the server's actions[]. A disabled action stays on
 * screen with its reason. Click -> pending state in the same tick (<= 100 ms);
 * the server's answer, not a guess, decides what shows next.
 */
import { loader, SLOW_MS } from "@/components/feedback";
import { h } from "@/lib/dom";

export interface BarState {
  confirming: null | string;
  pending: null | string;
  slow: boolean;
}

export interface BarHost {
  activate: (action: Action) => void;
  cancelConfirm: () => void;
  state: () => BarState;
}

export const idleBar = (): BarState => ({ confirming: null, pending: null, slow: false });

export function renderAction(action: Action, host: BarHost, taskId: string): HTMLElement {
  const state = host.state();
  if (state.confirming === action.id) {
    return h(
      "div",
      { attrs: { "aria-label": `Confirm ${action.label}`, role: "group" }, class: "action confirm" },
      h("span", { class: "confirm-text", text: `${action.label}: are you sure?` }),
      h("button", { attrs: { "data-confirm": "yes", type: "button" }, class: "btn primary", on: { click: () => { host.activate(action); } }, text: `Yes, ${action.label.toLowerCase()}` }),
      h("button", { attrs: { type: "button" }, class: "btn", on: { click: () => { host.cancelConfirm(); } }, text: "Back" }),
    );
  }
  const isBusy = state.pending === action.id;
  const isBlocked = !action.enabled || state.pending !== null;
  const reasonId = `reason-${taskId}-${action.id}`;
  return h(
    "div",
    { class: "action" },
    h("button", {
      attrs: {
        "aria-busy": isBusy,
        "aria-describedby": action.enabled ? null : reasonId,
        "aria-disabled": isBlocked,
        "data-action": action.id,
        type: "button",
      },
      class: `btn${action.id === "ship" || action.id === "start" ? " primary" : ""}${isBlocked ? " is-disabled" : ""}`,
      on: {
        click: () => {
          if (!isBlocked) host.activate(action);
        },
      },
      text: isBusy ? `${action.label}…` : action.label,
    }),
    !action.enabled && h("span", { attrs: { id: reasonId }, class: "reason", text: action.reason ?? "" }),
  );
}

export function pendingLoader(action: Action | undefined, taskId: string, state: BarState): HTMLElement | null {
  return state.pending === null || !state.slow ? null : loader(`Waiting for the server to finish: ${action?.label ?? state.pending} (task ${taskId})`);
}

export function slowTimer(onSlow: () => void): () => void {
  const timer = setTimeout(onSlow, SLOW_MS);
  return () => {
    clearTimeout(timer);
  };
}
