import type { NoteImage, TaskCard } from "@/lib/schemas-common";

import { h } from "@/lib/dom";
import { routes } from "@/lib/routes";

/** The note's images (T2535) as a thumbnail row in the drawer head; each opens full size in a new tab. */
export function noteImages(card: TaskCard): HTMLElement | null {
  if (card.images === undefined) {
    return null;
  }
  return h("div", { class: "note-images" }, ...card.images.map((image) => {
    const url = routes.image(image);
    return h("a", { attrs: { href: url, rel: "noopener", target: "_blank" } }, thumb(image, "note-thumb"));
  }));
}

/** The first image as the board tile's thumbnail (the tile is a button: no link inside it). */
export function tileImage(card: TaskCard): HTMLElement | null {
  const first = card.images?.[0];
  return first === undefined ? null : thumb(first, "card-thumb");
}

function thumb(image: NoteImage, cls: string): HTMLElement {
  return h("img", { attrs: { alt: image.file, decoding: "async", loading: "lazy", src: routes.image(image) }, class: cls });
}
