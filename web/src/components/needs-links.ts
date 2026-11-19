/** The pages a Needs-you ask names (`needs.links`, T2135): one link glyph each, the URL as its accessible name.
 * Only http(s) is ever linked, whatever the server sent; a link opens in a new tab and never hands over `opener`. */
import { icon } from "@/components/icons";
import { h } from "@/lib/dom";

const WEB = new Set(["http:", "https:"]);

function isWeb(url: string): boolean {
  try {
    const { protocol } = new URL(url);
    return WEB.has(protocol);
  } catch {
    return false;
  }
}

export function renderNeedsLinks(links: readonly string[] | undefined): HTMLElement | null {
  const shown = (links ?? []).filter((url) => isWeb(url));
  if (shown.length === 0) return null;
  return h(
    "p",
    { attrs: { "data-needs-links": "" }, class: "needs-links" },
    ...shown.map((url) => {
      const anchor = h("a", { attrs: { "aria-label": url, "data-needs-link": url, href: url, rel: "noopener noreferrer", target: "_blank", title: url }, class: "btn icon-btn" });
      anchor.append(icon("link"));
      return anchor;
    }),
  );
}
