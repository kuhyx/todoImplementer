import type { BarHost } from "@/components/action-bar";
import type { Action, ActionChoice } from "@/lib/schemas-common";

/**
 * The model picker (action `model`): one short button per server choice, the pinned one pressed. A click
 * sends {model: id}; the server pins it and runs the card's stage again on it (modelswitch).
 */
import { h } from "@/lib/dom";

export function renderPicker(action: Action, choices: ActionChoice[], host: BarHost, taskId: string): HTMLElement {
  const state = host.state();
  const isBlocked = !action.enabled || state.pending !== null;
  const reasonId = `reason-${taskId}-${action.id}`;
  const buttons = choices.map((choice) => {
    return h("button", {
      attrs: {
        "aria-busy": state.pending === action.id,
        "aria-describedby": action.enabled ? null : reasonId,
        "aria-disabled": isBlocked,
        "aria-pressed": choice.id === action.value,
        "data-action": action.id,
        "data-model": choice.id,
        type: "button",
      },
      class: `btn${isBlocked ? " is-disabled" : ""}`,
      on: {
        click: () => {
          if (!isBlocked && choice.id !== action.value) host.activate({ ...action, value: choice.id });
        },
      },
      text: choice.label,
    });
  },
  );
  return h(
    "div",
    { attrs: { "aria-label": action.label, role: "group" }, class: "action model-picker" },
    ...buttons,
    !action.enabled && h("span", { attrs: { id: reasonId }, class: "reason", text: action.reason ?? "" }),
  );
}
