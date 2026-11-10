/** Inline SVG icons (24 px grid, stroke = currentColor) and the icon-only button: its name lives in aria-label and title. */
import { h } from "@/lib/dom";

const NS = "http://www.w3.org/2000/svg";
const PATHS = {
  all: "M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01",
  back: "M19 12H5M11 6l-6 6 6 6",
  cheap: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM8.5 12h7",
  check: "M5 12.5l4.5 4.5L19 7.5",
  close: "M6 6l12 12M18 6L6 18",
  escalated: "M12 20V5M6 11l6-6 6 6",
  free: "M4 11h16v9H4zM3 7h18v4H3zM12 7v13M12 7c-2-4-5-3-4 0M12 7c2-4 5-3 4 0",
  info: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM12 11v5M12 8h.01",
  one: "M6 4h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM8 12h8",
} as const;

export type IconName = keyof typeof PATHS;

export function icon(name: IconName): SVGSVGElement {
  const svg = document.createElementNS(NS, "svg");
  const path = document.createElementNS(NS, "path");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  path.setAttribute("d", PATHS[name]);
  svg.append(path);
  return svg;
}

/** Swap the glyph and the accessible name of an icon button (a toggle changes both together). */
export function setIcon(button: HTMLElement, name: IconName, label: string): void {
  button.setAttribute("aria-label", label);
  button.title = label;
  button.replaceChildren(icon(name));
}

export function iconButton(name: IconName, label: string, attributes: Record<string, boolean | string>, click: () => void, extra = ""): HTMLButtonElement {
  const button = h("button", { attrs: { ...attributes, type: "button" }, class: `btn icon-btn ${extra}`.trim(), on: { click } });
  setIcon(button, name, label);
  return button;
}
