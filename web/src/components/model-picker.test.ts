import { describe, expect, it } from "vitest";

import type { Action } from "@/lib/schemas-common";

import { card, env, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { makeDetail } from "@/test/fixture-detail";
import { settle } from "@/test/net";

useDrawerHarness();

const CHOICES = [
  { id: "claude-fable-5-2", label: "Fable 5.2" },
  { id: "claude-opus-5-5", label: "Opus 5.5" },
  { id: "default", label: "Default" },
];
const PICKER: Action = { choices: CHOICES, enabled: true, id: "model", label: "Model", reason: null, value: "default" };

describe("model picker", () => {
  it("[T2219] shows the card's model, presses the pin and posts the picked model", async () => {
    const c = { ...card("working"), actions: [PICKER], model: "opus" };
    const pinned = { ...c, actions: [{ ...PICKER, value: "claude-fable-5-2" }], model: "claude-fable-5-2" };
    let state = c;
    await open(c, {
      [`GET /api/task/${c.id}`]: () => makeDetail(state),
      [`POST /api/task/${c.id}/model`]: () => {
        state = pinned;
        return { ok: true, task: pinned };
      },
    });
    expect(q(".drawer-chips [data-model]").textContent).toBe("opus");
    expect(q("[data-model=default]").getAttribute("aria-pressed")).toBe("true");
    q("[data-model=default]").click(); // the pinned one: nothing to send
    expect(env.stub.calls.filter((call) => call.init?.method === "POST")).toHaveLength(0);
    q("[data-model=claude-fable-5-2]").click();
    await settle(300);
    const post = env.stub.calls.find((call) => call.init?.method === "POST");
    expect(post?.url).toBe(`/api/task/${c.id}/model`);
    expect(post?.init?.body).toBe('{"model":"claude-fable-5-2"}');
    expect(q("[data-model=claude-fable-5-2]").getAttribute("aria-pressed")).toBe("true");
    expect(q(".drawer-chips [data-model]").textContent).toBe("claude-fable-5-2");
  });

  it("[T2219] a disabled picker names why and sends nothing", async () => {
    const c = { ...card("shipping"), actions: [{ ...PICKER, enabled: false, reason: "shipping is in progress" }] };
    await open(c, { [`GET /api/task/${c.id}`]: () => makeDetail(c) });
    q("[data-model=claude-opus-5-5]").click();
    expect(env.stub.calls.filter((call) => call.init?.method === "POST")).toHaveLength(0);
    expect(q(".model-picker .reason").textContent).toBe("shipping is in progress");
  });
});
