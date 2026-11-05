import { describe, expect, it } from "vitest";

import { DEFAULT_STATE, formatHash, parseHash } from "@/lib/hash-state";

describe("hash state", () => {
  it("round-trips a full state", () => {
    const state = { col: "ready", q: "fix it", repo: "utils", sort: "cost", task: "17a1b2c3-0" } as const;
    expect(parseHash(formatHash(state))).toEqual(state);
  });

  it("omits defaults", () => {
    expect(formatHash(DEFAULT_STATE)).toBe("");
    expect(parseHash("")).toEqual(DEFAULT_STATE);
  });

  it("falls back on garbage", () => {
    expect(parseHash("#sort=nope&col=x&task=short")).toEqual(DEFAULT_STATE);
  });

  it("keeps the yours marker", () => {
    expect(parseHash("#repo=-").repo).toBe("-");
  });
});
