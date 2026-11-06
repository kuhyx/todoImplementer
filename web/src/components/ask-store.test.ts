/** Question drafts in localStorage: round trip, bad data and blocked storage. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { blankState, dropState, loadState, saveState, storeKey } from "@/components/ask-store";
import { askQuestions } from "@/test/fixture-ask";

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ask store", () => {
  it("keys by card id and question ids", () => {
    expect(storeKey("c1", askQuestions(3))).toBe("todoimpl.ask.c1.Q1,Q2,Q3");
  });

  it("round-trips a state and drops it", () => {
    const state = { ...blankState(2), drafts: { Q1: "x" }, queued: true };
    saveState("k", state);
    expect(loadState("k")).toEqual(state);
    dropState("k");
    expect(loadState("k")).toBeNull();
  });

  it("ignores a value of the wrong shape or that is not JSON", () => {
    localStorage.setItem("k", '{"step":"x"}');
    expect(loadState("k")).toBeNull();
    localStorage.setItem("k", "not json");
    expect(loadState("k")).toBeNull();
  });

  it("survives blocked storage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("blocked");
    });
    expect(() => { saveState("k", blankState(0)); }).not.toThrow();
    expect(() => { dropState("k"); }).not.toThrow();
  });
});
