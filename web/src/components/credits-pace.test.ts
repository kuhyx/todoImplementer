import { describe, expect, it } from "vitest";

import { renderCreditsPace } from "@/components/credits-pace";
import { renderUsage } from "@/components/usage-strip";
import { makeCredits } from "@/test/fixture-credits";
import { makeBoard, NOW } from "@/test/fixtures";

const fill = (root: HTMLElement): string => root.querySelector<HTMLElement>(".c-fill")?.style.getPropertyValue("--fill") ?? "";

describe("credits pace strip", () => {
  it("[T2532] shows a spinner with the count of pending batches and the oldest's age", () => {
    expect(renderCreditsPace(makeCredits()).querySelector(".c-batch")).toBeNull();
    const pending = { est_usd: 0.02, oldest_at: 1_000, pending: 2 };
    const strip = renderCreditsPace(makeCredits({ batches: pending }), 1_000 + 300);
    const batch = strip.querySelector<HTMLElement>(".c-batch");
    expect(batch?.querySelector(".spinner")).not.toBeNull();
    expect(batch?.textContent).toBe("2");
    expect(batch?.title).toBe("Batch: 2 pending, oldest 5 min");
  });

  it("fills the bar with the spent share of the monthly grant", () => {
    expect(fill(renderCreditsPace(makeCredits({ spent_period_usd: 50 })))).toBe("25%");
    expect(fill(renderCreditsPace(makeCredits({ spent_period_usd: 999 })))).toBe("100%");
    expect(fill(renderCreditsPace(makeCredits({ monthly_usd: 0, spent_period_usd: 5 })))).toBe("0%");
  });

  it("puts a tick at each weekly cap and lights the current week's", () => {
    const strip = renderCreditsPace(makeCredits({ week: 3 }));
    const ticks = [...strip.querySelectorAll<HTMLElement>(".c-tick")];
    expect(ticks.map((tick) => tick.style.getPropertyValue("--at"))).toEqual(["25%", "50%", "75%", "100%"]);
    expect(ticks.map((tick) => tick.dataset.current)).toEqual(["false", "false", "true", "false"]);
  });

  it("shows only symbols and numbers, the estimate marked with an approx sign", () => {
    const strip = renderCreditsPace(makeCredits({ remaining_usd: 160, spent_period_usd: 40.5 }));
    expect(strip.textContent).toBe("≈$40.50 / $100.00≈$160.00");
    expect(strip.textContent).toMatch(/^[\d$≈ ./]+$/u);
  });

  it("names the fields and the route of the next turn in the tooltip", () => {
    const strip = renderCreditsPace(makeCredits());
    for (const part of ["estimate", "cap this week (2 of 4)", "monthly grant: $200.00", "remaining: $160.00", "credit turns: 12, running: 1", "next turn: credits"]) {
      expect(strip.title).toContain(part);
    }
    expect(strip.getAttribute("aria-label")).toBe(strip.title);
  });

  it("colours by the pace: ok, warn near the cap, danger at it, and marks a waiting route", () => {
    expect(renderCreditsPace(makeCredits()).dataset.tone).toBe("ok");
    expect(renderCreditsPace(makeCredits({ spent_period_usd: 85 })).dataset.tone).toBe("warn");
    const over = renderCreditsPace(makeCredits({ over_cap: true, route: null, spent_period_usd: 100 }));
    expect(over.dataset.tone).toBe("danger");
    expect(over.dataset.route).toBe("wait");
    expect(over.title).toContain("next turn: waits");
  });

  it("sits in the usage strip beside the credits toggle", () => {
    const strip = renderUsage(null, makeBoard(), null, null, NOW);
    expect(strip.querySelector(".credits-pace")).not.toBeNull();
    expect(renderUsage(null, null, null, null, NOW).querySelector(".credits-pace")).toBeNull();
  });
});
