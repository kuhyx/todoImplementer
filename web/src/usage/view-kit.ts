import type { Child } from "@/lib/dom";

import { h } from "@/lib/dom";

export interface Tile {
  label: string;
  value: string;
}

export function tiles(items: readonly Tile[]): HTMLElement {
  return h(
    "div",
    { class: "tiles" },
    ...items.map((tile) => h("div", { class: "tile" }, h("span", { class: "tile-label", text: tile.label }), h("strong", { class: "tile-value", text: tile.value }))),
  );
}

export function section(title: string, ...children: Child[]): HTMLElement {
  return h("section", { class: "panel" }, h("h2", { text: title }), ...children);
}

export function note(content: string): HTMLElement {
  return h("p", { class: "note", text: content });
}

const MARK = { green: "●", grey: "○", red: "▲" } as const;

/** Level is carried by a shape and the words, never colour alone. */
export function banner(level: keyof typeof MARK, content: string): HTMLElement {
  return h("p", { attrs: { "data-level": level }, class: "banner" }, h("span", { attrs: { "aria-hidden": "true" }, text: MARK[level] }), content);
}

export function grid(...children: Child[]): HTMLElement {
  return h("div", { class: "grid" }, ...children);
}

export function link(href: string, content: string): HTMLAnchorElement {
  return h("a", { attrs: { href }, text: content });
}

export const short = (text: string, limit = 80): string => (text.length > limit ? `${text.slice(0, limit - 1)}…` : text);
