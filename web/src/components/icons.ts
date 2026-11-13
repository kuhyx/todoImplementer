/** Inline SVG icons (24 px grid, stroke = currentColor) and the icon-only button: its name lives in aria-label and title. */
import { h } from "@/lib/dom";

const NS = "http://www.w3.org/2000/svg";
const PATHS = {
  all: "M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01",
  attention: "M6 17h12l-1.5-2v-4a4.5 4.5 0 0 0-9 0v4zM10 20a2 2 0 0 0 4 0",
  back: "M19 12H5M11 6l-6 6 6 6",
  cheap: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM8.5 12h7",
  check: "M5 12.5l4.5 4.5L19 7.5",
  chevron: "M6 9l6 6 6-6",
  circle: "M12 4a8 8 0 1 0 0 16a8 8 0 0 0 0-16z",
  close: "M6 6l12 12M18 6L6 18",
  coached: "M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10c1 1 1 2 1 3h6c0-1 0-2 1-3a6 6 0 0 0-4-10z",
  continuing: "M5 12h14M13 6l6 6-6 6",
  cooling: "M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9",
  copy: "M9 9h11v11H9zM5 15V4h11",
  done: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM8 12.5l3 3 5-6",
  escalated: "M12 20V5M6 11l6-6 6 6",
  eta: "M5 21V4M5 4h13l-3 4 3 4H5",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6a3 3 0 0 0 0-6z",
  failed: "M12 3l10 18H2zM12 10v5M12 18h.01",
  fixed: "M14 6a4 4 0 0 0-5 5l-6 6 3 3 6-6a4 4 0 0 0 5-5l-3 3-2-2z",
  folder: "M3 6h6l2 2h10v11H3z",
  free: "M4 11h16v9H4zM3 7h18v4H3zM12 7v13M12 7c-2-4-5-3-4 0M12 7c2-4 5-3 4 0",
  gateway: "M4 8h16v8H4zM8 8V5M16 8V5M8 16v3M16 16v3",
  hourglass: "M6 3h12M6 21h12M7 3c0 6 5 6 5 9s-5 3-5 9M17 3c0 6-5 6-5 9s5 3 5 9",
  info: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM12 11v5M12 8h.01",
  install: "M12 4v11M7 11l5 5 5-5M5 20h14",
  issue: "M9 8a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0zM4 9l5 2M20 9l-5 2M4 17l5-2M20 17l-5-2M9 5L7 3M15 5l2-2",
  killed: "M13 2L4 14h7l-1 8 9-12h-7z",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  lock: "M6 11h12v9H6zM8 11V8a4 4 0 0 1 8 0v3M12 15v2",
  log: "M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7",
  merge: "M6 4v5a5 5 0 0 0 5 5h7M6 20v-6M15 10l4 4-4 4",
  offline: "M2 9a15 15 0 0 1 20 0M5.5 12.5a10 10 0 0 1 13 0M9 16a5 5 0 0 1 6 0M12 19.5h.01M3 3l18 18",
  one: "M6 4h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM8 12h8",
  person: "M12 4a4 4 0 1 0 0 8a4 4 0 0 0 0-8zM4 21a8 8 0 0 1 16 0",
  photo: "M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6M15.5 8.5h.01",
  plus: "M12 5v14M5 12h14",
  qr: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 18h2v2h-2zM14 18h.01M18 14h.01",
  question: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01",
  queued: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM12 7v5l3 2",
  ready: "M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10",
  retry: "M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5",
  running: "M8 5v14l11-7z",
  search: "M11 4a7 7 0 1 0 0 14a7 7 0 0 0 0-14zM16 16l5 5",
  tag: "M3 12V3h9l9 9-9 9zM7.5 7.5h.01",
  terminal: "M3 5h18v14H3zM7 10l3 2-3 2M12 15h5",
  tokens: "M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3zM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6",
  trash: "M4 7h16M10 7V4h4v3M6 7l1 13h10l1-13M10 11v6M14 11v6",
  untagged: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM8 12h.01M12 12h.01M16 12h.01",
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
