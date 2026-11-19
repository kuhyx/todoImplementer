import { describe, expect, it } from "vitest";

import { renderCard, triageBadge } from "@/components/card";
import { renderHead } from "@/components/drawer-sections";
import { taskCard, TRIAGE_LABELS } from "@/lib/schemas-common";
import { contractValidator } from "@/test/contract-ajv";
import { card, useDrawerHarness } from "@/test/drawer-harness";
import { NOW } from "@/test/fixtures";

useDrawerHarness();

const badges = (element: Element): string[] => [...element.querySelectorAll("[data-triage]")].map((badge) => badge.getAttribute("data-triage") ?? "");

describe("triage badge", () => {
  it("[T2070] draws nothing for a card triage never saw", () => {
    expect(triageBadge(card("yours"))).toEqual([]);
    expect(badges(renderCard(card("yours"), NOW))).toEqual([]);
  });

  it("[T2070] draws one icon per label with no visible words, on the card and in the drawer head", () => {
    for (const label of TRIAGE_LABELS) {
      const shown = { ...card("yours"), triage: label };
      const element = renderCard(shown, NOW);
      expect(badges(element)).toEqual([label]);
      const badge = element.querySelector("[data-triage]");
      expect(badge?.querySelector("svg")).not.toBeNull();
      expect(badge?.textContent).toBe("");
      expect(badge?.getAttribute("role")).toBe("img");
      expect(badge?.getAttribute("aria-label")).toBeTruthy();
      expect(badge?.getAttribute("title")).toBe(badge?.getAttribute("aria-label"));
      expect(badges(renderHead({ card: shown } as never))).toEqual([label]);
    }
  });

  it("[T2070] the contract and the Zod mirror agree on the label", () => {
    const check = contractValidator("common", "task_card");
    const base = card("yours");
    for (const triage of [...TRIAGE_LABELS, "bogus", 3, undefined]) {
      const value = triage === undefined ? base : { ...base, triage };
      expect(taskCard.safeParse(value).success, String(triage)).toBe(check(value));
    }
  });
});
