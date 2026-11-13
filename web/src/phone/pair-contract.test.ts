/** The Zod mirror in pair-api.ts and contracts/pair.schema.json agree on a good fixture and on bad ones. */
import { describe, expect, it } from "vitest";

import { contractValidator } from "@/test/contract-ajv";

import { pairResponse } from "./pair-api";

function agree(value: unknown): boolean[] {
  return [contractValidator("pair")(value), pairResponse.safeParse(value).success];
}

const good = { expires_at: 1_900_000_300, url: "https://board.example.org/pair?c=AbCdEfGhIjKlMnOpQrStUv" };

describe("pair contract mirror", () => {
  it("accepts a good response in both", () => {
    expect(agree(good)).toEqual([true, true]);
  });

  it("rejects a missing field in both", () => {
    expect(agree({ url: good.url })).toEqual([false, false]);
    expect(agree({ expires_at: good.expires_at })).toEqual([false, false]);
  });

  it("rejects a non-integer expires_at in both", () => {
    expect(agree({ ...good, expires_at: 1.5 })).toEqual([false, false]);
    expect(agree({ ...good, expires_at: "300" })).toEqual([false, false]);
  });

  it("rejects an extra key in both", () => {
    expect(agree({ ...good, extra: 1 })).toEqual([false, false]);
  });
});
