import { afterEach, describe, expect, it, vi } from "vitest";

import { makeUsage } from "@/test/fixture-detail";
import { memoryContext } from "@/usage/context";
import { fakeFetch } from "@/usage/fixtures/load";
import { autonomyView, levelOf } from "@/usage/view-autonomy";

const { signal } = new AbortController();
const show = async (usage: unknown = makeUsage()): Promise<HTMLElement> => {
  vi.stubGlobal("fetch", vi.fn(fakeFetch({ "/api/usage": usage })));
  return autonomyView(memoryContext(""), signal);
};
const levels = (view: HTMLElement): (null | string)[] => [...view.querySelectorAll(".tile")].map((tile) => tile.getAttribute("data-level"));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("levelOf", () => {
  it("is green on the right side of the target for the direction, grey without a value", () => {
    expect(levelOf({ direction: "up", target: 100, value: 100 })).toBe("green");
    expect(levelOf({ direction: "up", target: 100, value: 40 })).toBe("red");
    expect(levelOf({ direction: "down", target: 0, value: 0 })).toBe("green");
    expect(levelOf({ direction: "down", target: 0, value: 1 })).toBe("red");
    expect(levelOf({ direction: "up", target: 100, value: null })).toBe("grey");
  });
});

describe("autonomy view", () => {
  it("shows four tiles with value against target, the words and a chart per metric", async () => {
    const view = await show();
    expect(levels(view)).toEqual(["red", "green", "red", "red"]);
    const [done, permissions] = [...view.querySelectorAll(".tile")];
    expect(done?.textContent).toContain("40%");
    expect(done?.textContent).toContain("off target · target 100%, higher is better · 2 of 5 finished cards");
    expect(permissions?.textContent).toContain("on target · target 0, lower is better");
    expect(view.querySelectorAll(".chart svg")).toHaveLength(4);
    expect(view.textContent).toContain("6 cards read, 3 of them from before the intervention record");
    expect(view.textContent).not.toMatch(/\[object Object\]|undefined|NaN/v);
  });

  it("shows a dash and a grey tile until a card has finished", async () => {
    const usage = makeUsage();
    usage.autonomy.done_unassisted = { count: 0, direction: "up", finished: 0, target: 100, value: null, weekly: [] };
    const view = await show(usage);
    expect(levels(view)[0]).toBe("grey");
    expect(view.querySelector(".tile")?.textContent).toContain("—");
    expect(view.querySelector(".tile")?.textContent).toContain("no data yet");
  });

  it("rejects a body that is not the contract", async () => {
    await expect(show({ autonomy: 1 })).rejects.toThrow("unexpected shape at autonomy");
  });
});
