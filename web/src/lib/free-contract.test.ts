/** The Zod mirror of free.schema.json and the contract must agree on the usage fixture, good and bad. */
import { describe, expect, it } from "vitest";

import { formatCompact } from "@/lib/format";
import { usage } from "@/lib/schemas";
import { contractValidator } from "@/test/contract-ajv";
import { makeUsage } from "@/test/fixture-detail";
import { makeFree } from "@/test/fixture-free";

function agree(value: unknown): boolean[] {
  return [contractValidator("usage")(value), usage.safeParse(value).success];
}

describe("free contract mirror", () => {
  it("accepts the usage fixture with a free reading, and without one", () => {
    expect(agree(makeUsage())).toEqual([true, true]);
    expect(agree({ ...makeUsage(), free: undefined })).toEqual([true, true]);
  });

  it("agrees on a never-read gateway", () => {
    const unread = { ...makeFree(), at: null, combo: null, counts: { cooling: 0, failing: 0, ok: 0, providers: 0, quota_known: 0 }, providers: [], quotas: [], state: "unknown", tokens: null };
    expect(agree({ ...makeUsage(), free: unread })).toEqual([true, true]);
  });

  it("rejects a bad state, an extra key and a quota without a total in both", () => {
    expect(agree({ ...makeUsage(), free: { ...makeFree(), state: "weird" } })).toEqual([false, false]);
    expect(agree({ ...makeUsage(), free: { ...makeFree(), extra: 1 } })).toEqual([false, false]);
    const quota = { label: "x", left_pct: 5, provider: "p", reset_at: null, total: 0, used: 0 };
    expect(agree({ ...makeUsage(), free: { ...makeFree(), quotas: [quota] } })).toEqual([false, false]);
  });
});

describe("formatCompact", () => {
  it("shortens token counts", () => {
    expect([950, 1000, 812_345, 4_123_700].map((n) => formatCompact(n))).toEqual(["950", "1k", "812k", "4.1M"]);
  });
});
