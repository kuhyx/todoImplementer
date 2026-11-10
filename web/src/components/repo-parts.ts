import type { RepoPart } from "@/lib/schemas-common";

/** Repo task parts: a state icon per part on the card, a checklist in the drawer, a lock when a run waits on another. Icons and numbers only; part titles are user content, names live in aria-label and title. */
import { icon, type IconName } from "@/components/icons";
import { h } from "@/lib/dom";

const STATE_ICON: Record<RepoPart["state"], IconName> = {
  done: "check",
  held: "link",
  human: "person",
  todo: "circle",
  working: "running",
};
const STATE_NAME: Record<RepoPart["state"], string> = {
  done: "Done",
  held: "Own run",
  human: "Yours",
  todo: "To do",
  working: "Working",
};

function stateMark(part: RepoPart): HTMLElement {
  const name = `${part.title}: ${STATE_NAME[part.state]}`;
  return h("span", { attrs: { "aria-label": name, "data-state": part.state, role: "img", title: name }, class: "p-mark" }, icon(STATE_ICON[part.state]));
}

/** Card line: one state icon per part, in the run's order. */
export function partsStrip(parts: readonly RepoPart[]): HTMLElement {
  return h("span", { attrs: { "data-parts": "" }, class: "p-strip" }, ...parts.map((part) => stateMark(part)));
}

function renderPart(part: RepoPart): HTMLElement {
  const steps = part.steps === null ? false : `${String(part.steps.done)}/${String(part.steps.total)}`;
  return h(
    "li",
    { attrs: { "data-id": part.id, "data-state": part.state }, class: "p-row" },
    stateMark(part),
    h("span", { class: "p-title", text: part.title }),
    steps !== false && h("span", { attrs: { "aria-label": `Steps ${steps}`, title: `Steps ${steps}` }, class: "p-steps" }, icon("width"), h("span", { class: "u-num", text: steps })),
  );
}

/** Drawer checklist of the parts. */
export function renderParts(parts: readonly RepoPart[]): HTMLElement {
  return h("section", { attrs: { "aria-label": "Parts", "data-parts-detail": "" }, class: "block p-detail" }, h("ul", { class: "p-rows" }, ...parts.map((part) => renderPart(part))));
}

/** A lock icon: this queued run waits on run `id` of the same repo. */
export function waitsBadge(id: string): HTMLElement {
  const text = `Waits on ${id}`;
  return h("span", { attrs: { "aria-label": text, "data-waits-on": id, role: "img", title: text }, class: "u-badge" }, icon("lock"));
}
