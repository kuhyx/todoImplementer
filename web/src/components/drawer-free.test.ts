/** The drawer for a plain Claude question (one-question view, send action) and the fixed-slot markup of the answer view. */
import { beforeEach, describe, expect, it } from "vitest";

import { card, env, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { freeDetail } from "@/test/fixture-ask";
import { makeDetail } from "@/test/fixture-detail";
import { settle } from "@/test/net";

useDrawerHarness();

beforeEach(() => {
  localStorage.clear();
});

const posts = (): string[] => env.stub.calls.filter((call) => call.init?.method === "POST").map((call) => call.init?.body as string);
const kids = (selector: string): string[] => [...q(selector).children].map((node) => node.className || node.tagName);

describe("plain Claude question", () => {
  it("[T1805] opens in the only-ask mode, answers with OK as a send POST and has no old free card", async () => {
    const c = freeDetail().card;
    await open(c, { [`GET /api/task/${c.id}`]: freeDetail(), [`POST /api/task/${c.id}/send`]: { ok: true, task: c } });
    expect(q(".drawer").classList.contains("drawer--only-ask")).toBe(true);
    expect(q("[data-details]").hidden).toBe(false);
    expect(document.querySelector("textarea[name=ask-send]")).toBeNull();
    // T2273: Send to Claude stays below the question, so a note needs no answer first.
    expect(q("[data-slot=send]").hidden).toBe(false);
    expect(document.querySelector("[data-ask-mode]")).toBeNull();
    const box = q<HTMLTextAreaElement>("textarea[name=Q1]");
    expect(document.activeElement).toBe(box);
    box.value = "use port 8790";
    box.dispatchEvent(new Event("input"));
    q("[data-ask=accept]").click();
    await settle(0);
    expect(posts()).toEqual(['{"text":"use port 8790"}']);
    expect(localStorage).toHaveLength(0);
  });
});

describe("answer view slots", () => {
  it("[T1806] puts title, question, answer and Back/OK into the slots the stylesheet pins", async () => {
    await open(card("needs_you"));
    expect(q(".drawer").classList.contains("drawer--only-ask")).toBe(true);
    expect(q(".drawer-scroll").contains(q("[data-slot=head] .drawer-title"))).toBe(true);
    expect(kids(".ask-step > .ask-center")).toEqual(["ask-q", "TEXTAREA", "ask-nav"]);
    expect(kids(".ask-q")).toEqual(["ask-title", "ask-body"]);
    expect(q("[data-slot=questions]").contains(q(".ask-center"))).toBe(true);
  });

  it("[T1806] puts the waiting note in the last slot, after Back/OK", async () => {
    const c = card("needs_you");
    await open(c, { [`GET /api/task/${c.id}`]: makeDetail({ ...c, actions: [] }) });
    expect(kids(".ask-center")).toEqual(["ask-q", "TEXTAREA", "ask-nav", "ask-reason"]);
  });
});
