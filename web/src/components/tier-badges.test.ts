import { describe, expect, it } from "vitest";

import { renderCard, tierBadges } from "@/components/card";
import { renderHead } from "@/components/drawer-sections";
import { taskCard } from "@/lib/schemas-common";
import { contractValidator } from "@/test/contract-ajv";
import { card, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { NOW } from "@/test/fixtures";

useDrawerHarness();

const NONE = { cheap: false, escalated: false, free: false };
const badges = (element: Element): string[] => [...element.querySelectorAll("[data-tier]")].map((badge) => badge.getAttribute("data-tier") ?? "");

describe("cheap-tier badges", () => {
  it("draws nothing for an ordinary card", () => {
    expect(tierBadges({ ...card("working"), tier: NONE })).toEqual([]);
    expect(badges(renderCard({ ...card("working"), tier: NONE }, NOW))).toEqual([]);
  });

  it("draws one icon per true flag, in a fixed order, with no visible words", () => {
    const element = renderCard({ ...card("working"), tier: { cheap: true, escalated: true, free: true } }, NOW);
    expect(badges(element)).toEqual(["cheap", "free", "escalated"]);
    for (const badge of element.querySelectorAll("[data-tier]")) {
      expect(badge.querySelector("svg")).not.toBeNull();
      expect(badge.textContent).toBe("");
      expect(badge.getAttribute("role")).toBe("img");
      expect(badge.getAttribute("aria-label")).toBeTruthy();
      expect(badge.getAttribute("title")).toBe(badge.getAttribute("aria-label"));
    }
  });

  it("draws just the flags the server set", () => {
    expect(badges(renderCard({ ...card("working"), tier: { cheap: true, escalated: false, free: false } }, NOW))).toEqual(["cheap"]);
    expect(badges(renderCard({ ...card("working"), tier: { cheap: true, escalated: true, free: false } }, NOW))).toEqual(["cheap", "escalated"]);
  });

  it("shows the same badges in the drawer header", async () => {
    await open({ ...card("working"), tier: { cheap: true, escalated: false, free: true } });
    expect(badges(q(".drawer-chips"))).toEqual(["cheap", "free"]);
  });

  it("renderHead takes the badges from the card", () => {
    const detail = { card: { ...card("working"), tier: { cheap: true, escalated: true, free: false } } };
    expect(badges(renderHead(detail as never))).toEqual(["cheap", "escalated"]);
  });

  it("the contract and the Zod mirror agree", () => {
    const check = contractValidator("common", "tier_badges");
    for (const value of [NONE, { cheap: true, escalated: true, free: true }, { cheap: true }, { ...NONE, extra: true }, { ...NONE, cheap: "yes" }]) {
      expect(taskCard.shape.tier.safeParse(value).success, JSON.stringify(value)).toBe(check(value));
    }
  });
});
