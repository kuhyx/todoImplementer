/** The Zod mirror and contracts/track.schema.json agree on the shared fixture, good and bad. */
import { describe, expect, it } from "vitest";

import { RESTING_KINDS, track } from "@/lib/schemas-track";
import { contractValidator } from "@/test/contract-ajv";
import { rawTrack } from "@/test/fixture-track";

function agree(value: unknown): boolean[] {
  return [contractValidator("track")(value), track.safeParse(value).success];
}

describe("track contract mirror", () => {
  it("accepts the shared sample in both", () => {
    expect(agree(rawTrack())).toEqual([true, true]);
  });

  it("rejects the same bad inputs in both", () => {
    const sample = rawTrack() as { kids: Record<string, unknown>[]; resting: unknown };
    expect(agree({ ...sample, surprise: 1 })).toEqual([false, false]);
    expect(agree({ ...sample, resting: { kind: "weather", until: null } })).toEqual([false, false]);
    expect(agree({ ...sample, kids: [{ ...sample.kids[0], issues: -1 }] })).toEqual([false, false]);
    expect(agree({ ...sample, kids: [{ ...sample.kids[0], id: "short" }] })).toEqual([false, false]);
    expect(agree({ ...sample, eta: { done: 0, left: 1, median: null, seconds: null, width: 0 } })).toEqual([false, false]);
  });

  it("lists the same resting kinds as the contract", () => {
    const schema = contractValidator("track", "resting").schema as { properties: { kind: { enum: string[] } } };
    expect([...RESTING_KINDS]).toEqual(schema.properties.kind.enum);
  });
});
