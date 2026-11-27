import { describe, expect, it } from "vitest";

import { renderUsage } from "@/components/usage-strip";
import { makeCredits } from "@/test/fixture-credits";
import { makeUsage } from "@/test/fixture-detail";
import { makeBoard, NOW } from "@/test/fixtures";

const board = makeBoard();
const lit = (hold: "all" | "low_medium" | "none"): string[] => {
  const limit = { active: false, credits: makeCredits(), until: null, weekly_hold: hold, weekly_used: hold === "none" ? null : 0.93 };
  const element = renderUsage(makeUsage(), { ...board, limit }, null, null, NOW);
  return [...element.querySelectorAll<HTMLElement>(".r-tick")].map((t) => `${t.dataset.at ?? ""}:${t.dataset.lit ?? ""}`);
};

describe("weekly reserve ticks", () => {
  it("[T2533] marks 90 and 95 on the 7 d meter and lights the held ones", () => {
    expect(lit("none")).toEqual(["90:false", "95:false"]);
    expect(lit("low_medium")).toEqual(["90:true", "95:false"]);
    expect(lit("all")).toEqual(["90:true", "95:true"]);
  });
});
