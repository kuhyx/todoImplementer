import { describe, expect, it } from "vitest";

import { renderUsage } from "@/components/usage-strip";

describe("the sessions link on the board", () => {
  it("is an icon link beside the usage link, named only by aria-label and title", () => {
    const strip = renderUsage(null, null, null, null, 0);
    const link = strip.querySelector<HTMLAnchorElement>("a.sessions-link")!;
    expect(link.getAttribute("href")).toBe("/sessions");
    expect(link.textContent).toBe("");
    expect(link.querySelector("svg")).not.toBeNull();
    expect(link.getAttribute("aria-label")).toBe(link.title);
    expect(link.title).not.toBe("");
    expect(link.previousElementSibling?.getAttribute("href")).toBe("/usage");
  });
});
