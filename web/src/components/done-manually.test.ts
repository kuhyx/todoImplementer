import { describe, expect, it } from "vitest";

import type { Action } from "@/lib/schemas-common";

import { statusChip } from "@/components/card";
import { card, env, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { makeDetail } from "@/test/fixture-detail";
import { preset } from "@/test/fixture-presets";
import { settle } from "@/test/net";

useDrawerHarness();

const DONE_MANUALLY: Action = { confirm: true, enabled: true, id: "done-manually", label: "Done manually", reason: null };

describe("done manually", () => {
  it("[T2064] asks first, posts the click, and the server's Done manually status replaces the card", async () => {
    const c = { ...card("backlog"), actions: [DONE_MANUALLY] };
    const done = { ...c, ...preset("done_manually", true) };
    let state = c;
    await open(c, {
      [`GET /api/task/${c.id}`]: () => makeDetail(state),
      [`POST /api/task/${c.id}/done-manually`]: () => {
        state = done;
        return { ok: true, task: done };
      },
    });
    q("[data-action=done-manually]").click();
    expect(q("[data-slot=actions]").textContent).toContain("Done manually: are you sure?");
    expect(env.stub.calls.filter((call) => call.init?.method === "POST")).toHaveLength(0);
    q("[data-confirm]").click();
    await settle(300);
    const post = env.stub.calls.find((call) => call.init?.method === "POST");
    expect(post?.url).toBe(`/api/task/${c.id}/done-manually`);
    expect(post?.init?.body).toBe("{}");
    expect(q(".drawer-chips .chip").textContent).toBe("Done manually");
    expect(q("[data-slot=actions]").textContent).not.toContain("Done manually: are you sure");
  });

  it("[T2064] the status chip tells it from a shipped card", () => {
    expect(statusChip("done_manually").textContent).toBe("Done manually");
    expect(statusChip("done").textContent).toBe("Done");
  });
});
