/** The Zod mirrors and contracts/*.schema.json must agree on every fixture, good and bad. */
import { describe, expect, it } from "vitest";

import { board, liveEvent, postResponse, taskDetail, usage, version } from "@/lib/schemas";
import { action, ACTION_IDS, COLUMN_IDS, NEEDS_KINDS, STAGES, STATUSES } from "@/lib/schemas-common";
import { contractEnum, contractValidator } from "@/test/contract-ajv";
import { ASK_IDS, askDetail, FREE_ID, freeDetail } from "@/test/fixture-ask";
import { LIVE_EVENTS, makeDetail, makeUsage } from "@/test/fixture-detail";
import { makeBoard, makeCards } from "@/test/fixtures";

function agree(file: string, schema: { safeParse: (v: unknown) => { success: boolean } }, value: unknown): boolean[] {
  return [contractValidator(file)(value), schema.safeParse(value).success];
}

describe("contract mirror", () => {
  it("accepts the board fixture in both", () => {
    expect(agree("board", board, makeBoard())).toEqual([true, true]);
  });

  it("accepts a board-level error in both", () => {
    const withError = { ...makeBoard(), error: { code: "internal", message: "todo MCP unreachable" } };
    expect(agree("board", board, withError)).toEqual([true, true]);
    expect(agree("board", board, { ...makeBoard(), error: null })).toEqual([true, true]);
  });

  it("agrees on the api_key banner field, good and bad", () => {
    const key = { expires: null, level: "warn", state: "expiring", text: "expires soon" };
    expect(agree("board", board, { ...makeBoard(), api_key: key })).toEqual([true, true]);
    expect(agree("board", board, { ...makeBoard(), api_key: { ...key, state: "weird" } })).toEqual([false, false]);
    expect(agree("board", board, { ...makeBoard(), api_key: { ...key, extra: 1 } })).toEqual([false, false]);
  });

  it("accepts every task detail fixture in both", () => {
    for (const card of makeCards()) {
      expect(agree("task", taskDetail, makeDetail(card))).toEqual([true, true]);
    }
  });

  it("accepts the real-shaped question fixtures in both", () => {
    for (const id of ASK_IDS) expect(agree("task", taskDetail, id === FREE_ID ? freeDetail() : askDetail(id))).toEqual([true, true]);
  });

  it("accepts usage, version and every live event in both", () => {
    expect(agree("usage", usage, makeUsage())).toEqual([true, true]);
    expect(agree("version", version, { build: "abc1234", version: "0.1.0" })).toEqual([true, true]);
    for (const event of LIVE_EVENTS) expect(agree("live", liveEvent, event)).toEqual([true, true]);
  });

  it("accepts both POST response shapes in both", () => {
    const [card] = makeCards();
    expect(agree("response", postResponse, { ok: true, task: card })).toEqual([true, true]);
    expect(agree("response", postResponse, { error: { code: "disabled", message: "no slot" }, ok: false })).toEqual([
      true,
      true,
    ]);
  });

  it("rejects the same bad inputs in both", () => {
    const disabledNoReason = { enabled: false, id: "ship", label: "Ship", reason: null };
    expect(contractValidator("common", "action")(disabledNoReason)).toBe(false);
    expect(action.safeParse(disabledNoReason).success).toBe(false);
    const threeColumns = { ...makeBoard(), columns: makeBoard().columns.slice(0, 3) };
    expect(agree("board", board, threeColumns)).toEqual([false, false]);
    const extra = { ...makeBoard(), surprise: 1 };
    expect(agree("board", board, extra)).toEqual([false, false]);
    expect(agree("version", version, { build: "", version: "1" })).toEqual([false, false]);
    const [card] = makeCards();
    expect(agree("response", postResponse, { ok: true, task: { ...card, id: "17a1b2c3" } })).toEqual([false, false]);
    expect(agree("response", postResponse, { ok: true, task: { ...card, id: "17a1b2c3-12" } })).toEqual([true, true]);
  });

  it("lists the same enums as the contract", () => {
    expect([...STAGES]).toEqual(contractEnum("common", "stage"));
    expect([...STATUSES]).toEqual(contractEnum("common", "status"));
    expect([...COLUMN_IDS]).toEqual(contractEnum("common", "column"));
    expect([...NEEDS_KINDS]).toEqual(contractEnum("common", "needs_kind"));
    const actionSchema = contractValidator("common", "action").schema as {
      properties: { id: { enum: string[] } };
    };
    expect([...ACTION_IDS]).toEqual(actionSchema.properties.id.enum);
  });
});
