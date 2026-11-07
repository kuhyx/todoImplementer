/** Bare http(s) URLs in untrusted note text as links; a link to this board stays on the page (its #hash). */
import { type Child, h } from "@/lib/dom";

const URL_PART = /(https?:\/\/[^\s<>"]+)/v;
const PUNCTUATION = new Set(["!", ")", ",", ".", ":", ";", "?"]);
const BOARD = /^https?:\/\/(?:127\.0\.0\.1:8786|agents\.kuhy\.duckdns\.org)\/(#.*)$/v;

function link(url: string): HTMLElement {
  const local = BOARD.exec(url)?.[1];
  const attributes = local === undefined ? { href: url, rel: "noopener noreferrer", target: "_blank" } : { href: local };
  return h("a", { attrs: attributes, text: url });
}

/** Sentence punctuation after a URL stays text: "see https://x.org/a." links https://x.org/a. */
function split(part: string): [string, string] {
  let end = part.length;
  while (end > 0 && PUNCTUATION.has(part.charAt(end - 1))) end -= 1;
  return [part.slice(0, end), part.slice(end)];
}

export function linkify(text: string): Child[] {
  return text.split(URL_PART).flatMap((part, index): Child[] => {
    if (index % 2 === 0) return part === "" ? [] : [part];
    const [url, trail] = split(part);
    return trail === "" ? [link(url)] : [link(url), trail];
  });
}
