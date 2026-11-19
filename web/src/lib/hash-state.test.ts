import { describe, expect, it } from "vitest";

import { DEFAULT_STATE, formatHash, parseHash } from "@/lib/hash-state";

describe("hash state", () => {
  it("round-trips a full state", () => {
    const state = { col: "running", q: "fix it", repo: "utils", sort: "cost", task: "17a1b2c3-0", umbrella: "2d0704cd-0" } as const;
    expect(parseHash(formatHash(state))).toEqual(state);
  });

  it("omits defaults", () => {
    expect(formatHash(DEFAULT_STATE)).toBe("");
    expect(parseHash("")).toEqual(DEFAULT_STATE);
  });

  it("falls back on garbage", () => {
    expect(parseHash("#sort=nope&col=x&task=short")).toEqual(DEFAULT_STATE);
  });

  it("reads and writes the umbrella tracking view, and drops a malformed id", () => {
    expect(parseHash("#umbrella=2d0704cd-0").umbrella).toBe("2d0704cd-0");
    expect(formatHash({ ...DEFAULT_STATE, umbrella: "2d0704cd-0" })).toBe("#umbrella=2d0704cd-0");
    expect(parseHash("#umbrella=nope").umbrella).toBeNull();
  });

  it("keeps the yours marker", () => {
    expect(parseHash("#repo=-").repo).toBe("-");
  });
});
