/** The icon buttons of one row and of the bulk bar. Every request goes through `perform`; the app shows the answer. */
import type { Action } from "@/sessions/api";
import type { Item } from "@/sessions/model";

import { iconButton } from "@/components/icons";
import { h } from "@/lib/dom";
import { label } from "@/sessions/labels";
import { MAX_RESUME } from "@/sessions/model";
import { copyButton, deleteButton, type Outcome, outcomeGlyph } from "@/sessions/parts";

export type Perform = (action: Action, body: Record<string, unknown>, key: string) => Promise<void>;

/** Resume opens a terminal on the desktop; a phone viewport hides it (CSS `.desktop-only`) and keeps the copy button. */
const DESKTOP = "desktop-only";

export function rowActions(item: Item, perform: Perform, outcome: Outcome | undefined, isBusy: boolean): HTMLElement {
  const body = { id: item.id };
  const buttons = [
    iconButton("terminal", label.resume, { disabled: isBusy }, () => { void perform("resume", body, item.id); }, DESKTOP),
    copyButton(() => item.resume_command, label.copy),
    // Only a hand mark can be undone; a session that tagged itself done has nothing to mark.
    item.mark === "manual"
      ? iconButton("retry", label.unmark, { disabled: isBusy }, () => { void perform("mark", { ...body, mark: null }, item.id); })
      : !item.done && iconButton("done", label.mark, { disabled: isBusy }, () => { void perform("mark", { ...body, mark: "done" }, item.id); }),
    deleteButton(1, isBusy, () => { void perform("delete", body, item.id); }),
    outcome !== undefined && outcomeGlyph(outcome),
  ];
  return h("div", { class: "row-actions" }, ...buttons);
}

export interface BulkState {
  commands: () => string;
  ids: string[];
  isBusy: boolean;
  onClear: () => void;
  outcome: Outcome | undefined;
}

/** The bar over the table while rows are selected (or an answer is waiting to be dismissed). */
export function bulkBar(state: BulkState, perform: Perform): HTMLElement {
  const { ids, isBusy } = state;
  const body = { ids };
  const isTooMany = ids.length > MAX_RESUME;
  const resume = iconButton("terminal", isTooMany ? label.resumeMax : label.resume, { disabled: isBusy || isTooMany }, () => { void perform("resume", body, "bulk"); }, DESKTOP);
  return h(
    "section",
    { attrs: { "aria-label": label.select }, class: "bulk-bar" },
    ids.length > 0 && h("strong", { class: "bulk-count", text: String(ids.length) }),
    ids.length > 0 && iconButton("done", label.mark, { disabled: isBusy }, () => { void perform("mark", { ids, mark: "done" }, "bulk"); }),
    ids.length > 0 && iconButton("retry", label.unmark, { disabled: isBusy }, () => { void perform("mark", { ids, mark: null }, "bulk"); }),
    ids.length > 0 && copyButton(state.commands, label.copyAll),
    ids.length > 0 && resume,
    ids.length > 0 && deleteButton(ids.length, isBusy, () => { void perform("delete", body, "bulk"); }),
    iconButton("close", label.clearSelection, {}, state.onClear),
    state.outcome !== undefined && outcomeGlyph(state.outcome),
  );
}
