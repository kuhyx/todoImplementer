/** Inline SVG icons (24 px grid, stroke = currentColor) and the icon-only button: its name lives in aria-label and title. */
import { h } from "@/lib/dom";

const NS = "http://www.w3.org/2000/svg";
const PATHS = {
  all: "M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01",
  back: "M19 12H5M11 6l-6 6 6 6",
  cheap: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM8.5 12h7",
  check: "M5 12.5l4.5 4.5L19 7.5",
  close: "M6 6l12 12M18 6L6 18",
  coached: "M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10c1 1 1 2 1 3h6c0-1 0-2 1-3a6 6 0 0 0-4-10z",
  escalated: "M12 20V5M6 11l6-6 6 6",
  failed: "M12 3l10 18H2zM12 10v5M12 18h.01",
  fixed: "M14 6a4 4 0 0 0-5 5l-6 6 3 3 6-6a4 4 0 0 0 5-5l-3 3-2-2z",
  free: "M4 11h16v9H4zM3 7h18v4H3zM12 7v13M12 7c-2-4-5-3-4 0M12 7c2-4 5-3 4 0",
  info: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM12 11v5M12 8h.01",
  issue: "M9 8a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0zM4 9l5 2M20 9l-5 2M4 17l5-2M20 17l-5-2M9 5L7 3M15 5l2-2",
  merge: "M6 4v5a5 5 0 0 0 5 5h7M6 20v-6M15 10l4 4-4 4",
  one: "M6 4h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM8 12h8",
  queued: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM12 7v5l3 2",
  ready: "M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10",
  running: "M8 5v14l11-7z",
  width: "M4 5h16M4 12h10M4 19h4",
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
