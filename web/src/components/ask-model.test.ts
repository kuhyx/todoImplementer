/** Pure model of the question flow: ask kind, effective answers, first open question, swipes, labels. */
import { describe, expect, it } from "vitest";

import { answersOf, askOf, effective, firstOpen, isOnlyAsk, nextOpen, sendingLabel, swipeOf, waitingNote } from "@/components/ask-model";
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

  it("shows only questions for a spec_questions card with questions", () => {
    expect(isOnlyAsk(askDetail(ASK_ID))).toBe(true);
    expect(isOnlyAsk(freeDetail())).toBe(false);
    expect(isOnlyAsk({ ...askDetail(ASK_ID), questions: [] })).toBe(false);
  });

  it("prefers the draft, then the saved answer, then the recommendation", () => {
    const [question] = askQuestions(1);
    expect(effective(question!, {})).toBe(question?.recommendation);
    expect(effective({ ...question!, answer: "Saved" }, {})).toBe("Saved");
    expect(effective({ ...question!, answer: "Saved" }, { Q1: "Mine" })).toBe("Mine");
  });

  it("starts on the first unanswered question and on 0 when all are answered", () => {
    const [a, b, c] = askQuestions(3);
    expect(firstOpen([a!, b!, c!])).toBe(0);
    expect(firstOpen([{ ...a!, answer: "x" }, { ...b!, answer: "y" }, c!])).toBe(2);
    expect(firstOpen([{ ...a!, answer: "x" }, { ...b!, answer: "" }, c!])).toBe(1);
    expect(firstOpen([{ ...a!, answer: "x" }])).toBe(0);
    expect(firstOpen([])).toBe(0);
  });

  it("walks to the next unanswered question and says -1 after the last", () => {
    const [a, b, c, d] = askQuestions(4);
    const list = [{ ...a!, answer: "x" }, b!, { ...c!, answer: "y" }, d!];
    expect(nextOpen(list, 0)).toBe(1);
    expect(nextOpen(list, 1)).toBe(3);
    expect(nextOpen(list, 3)).toBe(-1);
    expect(nextOpen([{ ...a!, answer: "" }, { ...b!, answer: "z" }], 0)).toBe(-1);
  });

  it("explains why OK cannot send yet", () => {
    expect(waitingNote("usage limit")).toBe("Cannot send yet: usage limit. Your answers are kept here and sent as soon as Claude can take them.");
    expect(waitingNote("")).toBe("Your answers are kept here and sent as soon as Claude can take them.");
  });

  it("builds the payload from every question and drops empty answers", () => {
    const [a, b] = askQuestions(2);
    expect(answersOf([a!, b!], { Q2: "  Two  " })).toEqual({ Q1: a?.recommendation, Q2: "Two" });
    expect(answersOf([a!, b!], { Q1: "  ", Q2: "" })).toEqual({});
  });

  it("reads a long, mostly horizontal move as a swipe", () => {
    expect(swipeOf(120, 10)).toBe("next");
    expect(swipeOf(-120, -10)).toBe("back");
    expect(swipeOf(79, 0)).toBeNull();
    expect(swipeOf(100, 60)).toBeNull();
  });

  it("labels progress and the sending loader", () => {
    expect(sendingLabel(10)).toBe("Sending 10 answers…");
    expect(sendingLabel(1)).toBe("Sending 1 answer…");
  });
});
