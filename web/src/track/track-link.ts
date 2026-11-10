/** The icon link that opens an umbrella's tracking view (`#umbrella=<card id>`); it is a real anchor, so back works. */
import { icon } from "@/components/icons";
import { h } from "@/lib/dom";
import { formatHash, type ViewState } from "@/lib/hash-state";

export const TRACK_LABEL = "Track this umbrella run";

/** Link from the board: keeps the board's filters so Back returns to the same view. */
export function trackHref(state: ViewState, id: string): string {
  return formatHash({ ...state, task: null, umbrella: id });
}

export function trackLink(href: string, extra = ""): HTMLAnchorElement {
  const link = h("a", { attrs: { "aria-label": TRACK_LABEL, href, title: TRACK_LABEL }, class: `track-link ${extra}`.trim() }, icon("all"));
  link.dataset.track = "";
  return link;
}
