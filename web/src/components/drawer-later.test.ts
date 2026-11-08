/** T1816: any Claude question opens the same full-browser answer view, even after every spec question was answered. */
import { beforeEach, describe, expect, it } from "vitest";

import { env, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { laterDetail } from "@/test/fixture-ask";
import { settle } from "@/test/net";

useDrawerHarness();

beforeEach(() => {
  localStorage.clear();
});

const posts = (): string[] => env.stub.calls.filter((call) => call.init?.method === "POST").map((call) => call.init?.body as string);
const answer = (name: string, value: string): void => {
  const box = q<HTMLTextAreaElement>(`textarea[name=${name}]`);
  box.value = value;
  box.dispatchEvent(new Event("input"));
  q("[data-ask=accept]").click();
};

describe("a Claude question after the spec was answered", () => {
  it("[T1816] opens the only-ask view on the reply's cards, not on old answered spec questions", async () => {
    const detail = laterDetail();
    await open(detail.card, { [`GET /api/task/${detail.card.id}`]: detail });
    expect(q(".drawer").classList.contains("drawer--only-ask")).toBe(true);
    expect(q(".ask-title").textContent).toBe(`Q1 · ${detail.asks[0]?.title ?? ""}`);
    expect(q(".ask-body").textContent).toBe(detail.asks[0]?.body);
    expect(document.activeElement).toBe(q("textarea[name=Q1]"));
  });

  it("[T1816] OK walks every card, then sends all answers as one message", async () => {
    const detail = laterDetail();
    const c = detail.card;
    await open(c, { [`GET /api/task/${c.id}`]: detail, [`POST /api/task/${c.id}/send`]: { ok: true, task: c } });
    answer("Q1", "count it");
    await settle(0);
    expect(posts()).toEqual([]);
    answer("Q2", "no pacing");
    await settle(0);
    const text = `Q1 (${detail.asks[0]?.title ?? ""}): count it\n\nQ2 (${detail.asks[1]?.title ?? ""}): no pacing`;
    expect(posts()).toEqual([JSON.stringify({ text })]);
  });

  it("[T1816] without parsed cards the card's question text is the one question", async () => {
    const detail = laterDetail(0);
    await open(detail.card, { [`GET /api/task/${detail.card.id}`]: detail });
    expect(q(".drawer").classList.contains("drawer--only-ask")).toBe(true);
    expect(q(".ask-body").textContent).toBe(detail.card.needs?.text);
  });
});
