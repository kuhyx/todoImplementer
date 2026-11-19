import { afterEach, describe, expect, it } from "vitest";

import { renderNeeds } from "@/components/drawer-sections";
import { renderNeedsLinks } from "@/components/needs-links";
import { needs } from "@/lib/schemas-common";
import { makeDetail } from "@/test/fixture-detail";
import { makeCards } from "@/test/fixtures";

afterEach(() => {
  document.body.replaceChildren();
});

const LAB = "https://kuhy.duckdns.org/logo-lab";

describe("needs links", () => {
  it("[T2135] each link is a glyph that opens the absolute URL in a new tab", () => {
    const node = renderNeedsLinks([LAB, "http://127.0.0.1:4321/x"]);
    const anchors = node?.querySelectorAll("a") ?? [];
    expect(anchors).toHaveLength(2);
    expect(anchors[0]?.getAttribute("href")).toBe(LAB);
    expect(anchors[0]?.getAttribute("target")).toBe("_blank");
    expect(anchors[0]?.getAttribute("rel")).toBe("noopener noreferrer");
    expect(anchors[0]?.getAttribute("aria-label")).toBe(LAB);
    expect(anchors[0]?.querySelector("svg")).not.toBeNull();
    expect(node?.textContent).toBe("");
  });

  it("[T2135] only http and https are linked, and no links draws nothing", () => {
    expect(renderNeedsLinks(["javascript:alert(1)", "file:///etc/passwd", "not a url"])).toBeNull();
    expect(renderNeedsLinks([])).toBeNull();
    expect(renderNeedsLinks(undefined)).toBeNull();
    expect(renderNeedsLinks(["javascript:alert(1)", LAB])?.querySelectorAll("a")).toHaveLength(1);
  });

  it("[T2135] the drawer's need box carries the links of its ask", () => {
    const base = makeDetail(makeCards().find((card) => card.status === "needs_you") ?? makeCards()[0]!);
    const withLinks = { category: "action" as const, effort: 3, kind: "claude_action" as const, links: [LAB], text: "Pick one." };
    const node = renderNeeds({ ...base, card: { ...base.card, needs: withLinks } });
    expect(node?.querySelector(`a[data-needs-link="${CSS.escape(LAB)}"]`)).not.toBeNull();
    expect(renderNeeds(base)?.querySelector("[data-needs-links]")).toBeNull();
  });

  it("[T2135] the contract accepts links only as absolute http(s) URLs, one to five", () => {
    const row = { category: "action", effort: 3, kind: "claude_action", text: "Pick one." };
    expect(needs.safeParse({ ...row, links: [LAB] }).success).toBe(true);
    expect(needs.safeParse({ ...row, links: [] }).success).toBe(false);
    expect(needs.safeParse({ ...row, links: ["/logo-lab"] }).success).toBe(false);
    expect(needs.safeParse({ ...row, links: Array.from({ length: 6 }, (_, index) => `${LAB}${String(index)}`) }).success).toBe(false);
  });
});
