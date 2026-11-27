import type { BarHost } from "@/components/action-bar";
import type { Action } from "@/lib/schemas-common";

/**
 * The priority picker (action `priority`, T2583): one icon button per level, the card's priority pressed. Names
 * live in aria-label and title only (textgate). A click sends {priority}; the server sets it on every note behind
 * the card. A disabled picker (a card of only other apps' reports) names why.
 */
import { icon, type IconName } from "@/components/icons";
import { h } from "@/lib/dom";

const GLYPH: Record<string, IconName> = { high: "prioHigh", low: "prioLow", medium: "prioMedium" };

export function priorityGlyph(priority: string): IconName {
  return GLYPH[priority] ?? "prioMedium";
}

export function renderPriority(action: Action, host: BarHost, taskId: string): HTMLElement {
  const state = host.state();
  const isBlocked = !action.enabled || state.pending !== null;
  const reasonId = `reason-${taskId}-${action.id}`;
  const buttons = (action.choices ?? []).map((choice) => {
    return h("button", {
      attrs: {
        "aria-busy": state.pending === action.id,
        "aria-describedby": action.enabled ? null : reasonId,
        "aria-disabled": isBlocked,
        "aria-label": choice.label,
        "aria-pressed": choice.id === action.value,
        "data-action": action.id,
        "data-priority": choice.id,
        title: choice.label,
        type: "button",
      },
      class: `btn icon-btn${isBlocked ? " is-disabled" : ""}`,
      on: {
        click: () => {
          if (!isBlocked && choice.id !== action.value) host.activate({ ...action, value: choice.id });
        },
      },
    }, icon(priorityGlyph(choice.id)));
  });
  return h(
    "div",
    { attrs: { "aria-label": action.label, role: "group" }, class: "action priority-picker" },
    ...buttons,
    !action.enabled && h("span", { attrs: { id: reasonId }, class: "reason", text: action.reason ?? "" }),
  );
}
