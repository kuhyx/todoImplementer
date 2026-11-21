import { describe, expect, it } from "vitest";

import type { PeerMessage } from "@/lib/schemas-peer";

import { liveEvent } from "@/lib/schemas";
import { card, env, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { makeDetail } from "@/test/fixture-detail";
import { NOW } from "@/test/fixtures";
import { lastSource } from "@/test/net";

useDrawerHarness();

const c = card("working");
const row = (over: Partial<PeerMessage> = {}): PeerMessage => {
  return {
  answered_at: null, at: NOW - 60, card: c.id, delivered_at: null, from: "probe#1a2b", from_id: "1a2b", hop: 1,
  id: `${c.id}.0123456789ab`, reason: null, reply: null, reply_to: null, state: "queued", text: "which port?",
  to: `task:${c.id}#9f9f`, to_card: c.id, to_id: "9f9f", ...over,
  };
};

describe("peer live events", () => {
  it("[T2473] a peer event updates or adds the row at once, with no refetch", async () => {
    await open(c, { [`GET /api/task/${c.id}`]: () => ({ ...makeDetail(c), peer: [row()] }) });
    const gets = env.stub.calls.length;
    const answered = { message: row({ answered_at: NOW, reply: "8790", state: "answered" }), type: "peer" };
    expect(liveEvent.safeParse(answered).success).toBe(true);
    lastSource().emit("peer", answered);
    expect(q(`[data-peer="${c.id}.0123456789ab"]`).dataset.state).toBe("answered");
    expect(q("[data-reply]").textContent).toBe("8790");
    lastSource().emit("peer", { message: row({ id: `${c.id}.aaaaaaaaaaaa`, text: "second" }), type: "peer" });
    expect(env.drawer.querySelectorAll(".peer-row")).toHaveLength(2);
    expect(env.stub.calls).toHaveLength(gets);
  });
});
