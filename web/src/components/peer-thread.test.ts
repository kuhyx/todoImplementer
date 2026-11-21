import { describe, expect, it } from "vitest";

import type { PeerMessage } from "@/lib/schemas-peer";

import { renderPeer } from "@/components/peer-thread";
import { taskDetail } from "@/lib/schemas";
import { contractValidator } from "@/test/contract-ajv";
import { makeDetail } from "@/test/fixture-detail";
import { makeCards, NOW } from "@/test/fixtures";

const CARD = "abcd1234-0";

function message(over: Partial<PeerMessage> = {}): PeerMessage {
  return {
    answered_at: null, at: NOW - 60, card: CARD, delivered_at: null, from: "leetcode-guard#1a2b", from_id: "1a2b",
    hop: 1, id: `${CARD}.0123456789ab`, reason: null, reply: null, reply_to: null, state: "queued", text: "which port?",
    to: `task:${CARD}#9f9f`, to_card: CARD, to_id: "9f9f", ...over,
  };
}

const THREAD: PeerMessage[] = [
  message({ answered_at: NOW, delivered_at: NOW - 30, reply: "8790", state: "answered" }),
  message({ delivered_at: NOW, id: `${CARD}.aaaaaaaaaaaa`, state: "delivered", text: "second" }),
  message({ id: `${CARD}.bbbbbbbbbbbb`, reason: "not delivered in 30 min", state: "expired", text: "late" }),
  message({ hop: 7, id: `${CARD}.cccccccccccc`, reason: "over 6 hops", state: "dead_end", text: "bounce" }),
];

describe("peer thread", () => {
  it("is absent without messages", () => {
    const [card] = makeCards();
    expect(card).toBeDefined();
    if (card === undefined) return;
    expect(renderPeer(makeDetail(card))).toBeNull();
  });

  it("shows sender, recipient, text, state, reply and times, data only", () => {
    const [card] = makeCards();
    if (card === undefined) return;
    const node = renderPeer({ ...makeDetail(card), peer: THREAD });
    expect(node).not.toBeNull();
    const rows = [...(node?.querySelectorAll("[data-peer]") ?? [])];
    expect(rows.map((row) => row.getAttribute("data-state"))).toEqual(["answered", "delivered", "expired", "dead_end"]);
    const first = rows[0];
    expect(first?.querySelector("[data-from]")?.textContent).toBe("leetcode-guard#1a2b");
    expect(first?.querySelector("[data-to]")?.textContent).toBe(`task:${CARD}#9f9f`);
    expect(first?.querySelector("[data-text]")?.textContent).toBe("which port?");
    expect(first?.querySelector("[data-reply]")?.textContent).toBe("8790");
    expect(first?.querySelectorAll("time")).toHaveLength(3);
    expect(rows[1]?.querySelector("[data-reply]")).toBeNull();
    expect(rows[2]?.querySelector("[data-reason]")?.textContent).toBe("not delivered in 30 min");
    expect(rows[3]?.querySelector("svg")).not.toBeNull();
    expect(node?.getAttribute("aria-label")).toBe("Peer");
  });

  it("the thread matches the contract in both mirrors", () => {
    const [card] = makeCards();
    if (card === undefined) return;
    const detail = { ...makeDetail(card), peer: THREAD };
    expect([contractValidator("task")(detail), taskDetail.safeParse(detail).success]).toEqual([true, true]);
    const bad = { ...detail, peer: [{ ...message(), state: "lost" }] };
    expect([contractValidator("task")(bad), taskDetail.safeParse(bad).success]).toEqual([false, false]);
  });
});
