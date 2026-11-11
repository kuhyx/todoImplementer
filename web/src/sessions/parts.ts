/** Small icon-only parts shared by rows and the bulk bar: status pill, outcome mark, copy button, two-step delete. */
import type { Mark, Status } from "@/sessions/schemas";

import { icon, iconButton, setIcon } from "@/components/icons";
import { h } from "@/lib/dom";
import { label, MARK_ICON, MARK_LABEL, STATUS_ICON, STATUS_LABEL, STATUS_TONE } from "@/sessions/labels";

export const ARMED_MS = 5000;
export const COPIED_MS = 1500;
/** Bubbles from a delete button that timed out, so the page can apply a redraw it held back. */
export const DISARM = "disarm";

export interface Outcome {
  kind: "failed" | "ok" | "refused";
  summary: string;
}

const OUTCOME_ICON = { failed: "failed", ok: "check", refused: "lock" } as const;

/** The status as a round pill: tone + glyph, its name in `title` and `aria-label`. */
export function statusPill(status: Status): HTMLElement {
  const pill = h("span", { attrs: { "aria-label": STATUS_LABEL[status], "data-status": status, "data-tone": STATUS_TONE[status], role: "img", title: STATUS_LABEL[status] }, class: "pill" });
  pill.append(icon(STATUS_ICON[status]));
  return pill;
}

export function markGlyph(mark: Mark): HTMLElement {
  const glyph = h("span", { attrs: { "aria-label": MARK_LABEL[mark], "data-mark": mark, role: "img", title: MARK_LABEL[mark] }, class: "mark" });
  glyph.append(icon(MARK_ICON[mark]));
  return glyph;
}

/** What the server answered, as a glyph: its own words are the `title`, never visible text. */
export function outcomeGlyph(outcome: Outcome): HTMLElement {
  const glyph = h("span", { attrs: { "aria-label": outcome.summary, "data-kind": outcome.kind, role: "status", title: outcome.summary }, class: "outcome" });
  glyph.append(icon(OUTCOME_ICON[outcome.kind]));
  return glyph;
}

/** Copy `text()` to the clipboard: the glyph turns into a check (or a warning) for a moment instead of a toast. */
export function copyButton(text: () => string, name: string): HTMLButtonElement {
  const flash = (glyph: "check" | "failed", shown: string): void => {
    setIcon(button, glyph, shown);
    setTimeout(() => { setIcon(button, "copy", name); }, COPIED_MS);
  };
  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(text());
      flash("check", name);
    } catch {
      flash("failed", label.copyFailed);
    }
  };
  const button = iconButton("copy", name, {}, () => { void copy(); });
  return button;
}

/** Two clicks to delete: the first arms (red, with the count as a number), the second within five seconds sends. */
export function deleteButton(count: number, isDisabled: boolean, onConfirm: () => void): HTMLButtonElement {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const button = iconButton("trash", label.delete, { disabled: isDisabled }, () => {
    if (button.dataset.armed === "true") {
      clearTimeout(timer);
      onConfirm();
      return;
    }
    button.dataset.armed = "true";
    button.title = `${label.armed} (${String(count)})`;
    button.setAttribute("aria-label", button.title);
    button.append(h("span", { class: "armed-count", text: String(count) }));
    timer = setTimeout(() => {
      delete button.dataset.armed;
      setIcon(button, "trash", label.delete);
      button.dispatchEvent(new Event(DISARM, { bubbles: true }));
    }, ARMED_MS);
  });
  return button;
}
