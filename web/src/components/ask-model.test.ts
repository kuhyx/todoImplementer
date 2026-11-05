/** Pure render model of the question UI: layout, page fitting, pager and the Send answers payload. */
import { describe, expect, it } from "vitest";

import {
  answersOf, askOf, clampPager, effective, firstPage, fitCount, isLast, layoutFor, nextPage, pageLabel, previousPage,
} from "@/components/ask-model";
import { ASK_ID, askDetail, askQuestions, FREE_ID, freeDetail } from "@/test/fixture-ask";
import { makeDetail } from "@/test/fixture-detail";
import { makeCards } from "@/test/fixtures";

describe("ask model", () => {
  it("picks the ask kind from the detail", () => {
    expect(askOf(askDetail(ASK_ID))).toEqual({ kind: "spec", questions: askQuestions(5) });
    expect(askOf(freeDetail())).toEqual({ kind: "free", text: "Claude asked a question: answer it with Send to Claude" });
    const working = makeCards().find((card) => card.status === "working");
    expect(askOf(makeDetail(working ?? makeCards()[0]!))).toBeNull();
    expect(FREE_ID).not.toBe(ASK_ID);
  });

  it("steps on a phone and uses 1, 2 or 3 columns elsewhere", () => {
    expect(layoutFor(360)).toEqual({ cols: 1, mode: "step" });
    expect(layoutFor(479)).toEqual({ cols: 1, mode: "step" });
    expect(layoutFor(480)).toEqual({ cols: 1, mode: "grid" });
    expect(layoutFor(760)).toEqual({ cols: 2, mode: "grid" });
    expect(layoutFor(1100)).toEqual({ cols: 3, mode: "grid" });
    expect(layoutFor(5000)).toEqual({ cols: 3, mode: "grid" });
  });

  it("counts the leading cards that end inside the area, at least one", () => {
    expect(fitCount([], 500)).toBe(0);
    expect(fitCount([300, 300, 300, 620, 620], 640)).toBe(5);
    expect(fitCount([300, 300, 300, 620, 620], 600)).toBe(3);
    expect(fitCount([700, 700], 600)).toBe(1);
    expect(fitCount([300, 700, 300], 600)).toBe(1);
    expect(fitCount([600.4], 600)).toBe(1);
  });

  it("pages forward and back over measured counts", () => {
    let pager = firstPage;
    expect(pager).toEqual({ back: [], start: 0 });
    pager = nextPage(pager, 6, 9);
    expect(pager).toEqual({ back: [0], start: 6 });
    expect(nextPage(pager, 3, 9)).toBe(pager);
    expect(previousPage(pager)).toEqual({ back: [], start: 0 });
    expect(previousPage(firstPage)).toBe(firstPage);
    expect(clampPager(pager, 9)).toBe(pager);
    expect(clampPager(pager, 5)).toBe(firstPage);
  });

  it("labels the page, empty when one page holds everything", () => {
    expect(pageLabel("grid", 0, 5, 5)).toBe("");
    expect(pageLabel("grid", 0, 6, 9)).toBe("1–6 of 9");
    expect(pageLabel("grid", 6, 3, 9)).toBe("7–9 of 9");
    expect(pageLabel("grid", 8, 1, 9)).toBe("9 of 9");
    expect(pageLabel("step", 2, 1, 5)).toBe("3 / 5");
    expect(pageLabel("step", 0, 1, 1)).toBe("");
    expect(isLast(6, 3, 9)).toBe(true);
    expect(isLast(0, 6, 9)).toBe(false);
  });

  it("sends every answer, recommended or edited, in one payload", () => {
    const questions = askQuestions(3);
    const answered = [{ ...questions[0]!, answer: "Already answered" }, questions[1]!, { ...questions[2]!, recommendation: "" }];
    expect(effective(answered[0]!, new Map())).toBe("Already answered");
    expect(effective(answered[1]!, new Map())).toBe(questions[1]!.recommendation);
    expect(effective(answered[1]!, new Map([["Q2", "mine"]]))).toBe("mine");
    expect(answersOf(answered, new Map([["Q2", "  mine  "]]))).toEqual({ Q1: "Already answered", Q2: "mine" });
    expect(answersOf(questions, new Map([["Q1", "  "]]))).toEqual({ Q2: questions[1]!.recommendation, Q3: questions[2]!.recommendation });
  });
});
