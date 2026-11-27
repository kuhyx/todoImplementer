import { describe, expect, it } from "vitest";

import type { Action } from "@/lib/schemas-common";

import { priorityGlyph } from "@/components/priority-picker";
import { card, env, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { makeDetail } from "@/test/fixture-detail";
import { settle } from "@/test/net";

useDrawerHarness();

const CHOICES = [
  { id: "high", label: "High" },
  { id: "medium", label: "Medium" },
  { id: "low", label: "Low" },
];
const PICKER: Action = { choices: CHOICES, enabled: true, id: "priority", label: "Priority", reason: null, value: "medium" };
const posts = (): number => env.stub.calls.filter((call) => call.init?.method === "POST").length;

describe("priority picker", () => {
  it("[T2583] presses the card's priority and posts a pick", async () => {
    const c = { ...card("backlog"), actions: [PICKER] };
    const raised = { ...c, actions: [{ ...PICKER, value: "high" }], priority: "high" };
    let state = c;
    await open(c, {
      [`GET /api/task/${c.id}`]: () => makeDetail(state),
      [`POST /api/task/${c.id}/priority`]: () => {
        state = raised;
        return { ok: true, task: raised };
      },
    });
    const medium = q("[data-priority=medium]");
    expect(medium.getAttribute("aria-pressed")).toBe("true");
    expect([medium.getAttribute("aria-label"), medium.textContent]).toEqual(["Medium", ""]); // a glyph, no text
    medium.click(); // the pressed one: nothing to send
    expect(posts()).toBe(0);
    q("[data-priority=high]").click();
    await settle(300);
    const post = env.stub.calls.find((call) => call.init?.method === "POST");
    expect(post?.url).toBe(`/api/task/${c.id}/priority`);
    expect(post?.init?.body).toBe('{"priority":"high"}');
    expect(q("[data-priority=high]").getAttribute("aria-pressed")).toBe("true");
  });

  it("[T2583] a disabled picker names why and sends nothing", async () => {
    const off = { ...PICKER, enabled: false, reason: "other apps' error reports always run last; Start runs them now", value: "low" };
    await open({ ...card("backlog"), actions: [off] });
    q("[data-priority=high]").click();
    expect(posts()).toBe(0);
    expect(q(".priority-picker .reason").textContent).toContain("always run last");
    expect(q("[data-priority=high]").getAttribute("aria-describedby")).toMatch(/^reason-/v);
  });

  it("[T2583] a picker with no rows draws only its group; an odd level draws the middle glyph", async () => {
    await open({ ...card("backlog"), actions: [{ ...PICKER, choices: undefined }] });
    expect(q(".priority-picker").children).toHaveLength(0);
    expect(priorityGlyph("someday")).toBe("prioMedium");
    expect(priorityGlyph("low")).toBe("prioLow");
  });
});
