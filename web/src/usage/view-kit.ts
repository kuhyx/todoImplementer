import type { Child } from "@/lib/dom";

import { h } from "@/lib/dom";

const MARK = { green: "●", grey: "○", red: "▲" } as const;

export interface Tile {
  label: string;
  level?: keyof typeof MARK;
  note?: string;
  value: string;
}

function tileElement(tile: Tile): HTMLElement {
  const mark = tile.level === undefined ? false : h("span", { attrs: { "aria-hidden": "true" }, class: "tile-mark", text: `${MARK[tile.level]} ` });
  return h(
    "div",
    { attrs: { "data-level": tile.level }, class: "tile" },
    h("span", { class: "tile-label", text: tile.label }),
    h("strong", { class: "tile-value" }, mark, tile.value),
    tile.note !== undefined && h("span", { class: "tile-note", text: tile.note }),
  );
}

export function tiles(items: readonly Tile[]): HTMLElement {
  return h(
    "div",
    { class: "tiles" },
    ...items.map((tile) => tileElement(tile)),
  );
}

export function section(title: string, ...children: Child[]): HTMLElement {
  return h("section", { class: "panel" }, h("h2", { text: title }), ...children);
}

export function note(content: string): HTMLElement {
  return h("p", { class: "note", text: content });
}

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
