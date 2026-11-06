/** The drawer's question flow: only questions by default, Details toggle, Enter-accept flow, one POST, retry and persisted drafts. */
import { beforeEach, describe, expect, it } from "vitest";

import { card, env, fail, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { makeDetail } from "@/test/fixture-detail";
import { settle } from "@/test/net";

useDrawerHarness();

beforeEach(() => {
  localStorage.clear();
});

const field = (): HTMLTextAreaElement => q<HTMLTextAreaElement>("textarea[name]");
const enter = (): void => {
  field().dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Enter" }));
};
const posts = (): string[] => env.stub.calls.filter((call) => call.init?.method === "POST").map((call) => call.init?.body as string);

describe("question card", () => {
  it("opens on the questions only, with a focused prefilled answer and one Details toggle", async () => {
    await open(card("needs_you"));
    expect(q(".drawer").classList.contains("drawer--only-ask")).toBe(true);
    expect(q("[data-tab=questions]").getAttribute("aria-pressed")).toBe("true");
    expect(q("[data-details]").hidden).toBe(false);
    expect(q("[data-details]").textContent).toBe("Details");
    expect(document.activeElement).toBe(field());
    expect(field().value).toBe("localStorage");
    expect(document.querySelector("[data-action=spec-answers]")).toBeNull();
  });

  it("brings the tabs back behind Details and returns to the questions when closed again", async () => {
    await open(card("needs_you"));
    q("[data-details]").click();
    expect(q(".drawer").classList.contains("drawer--only-ask")).toBe(false);
    expect(q("[data-details]").textContent).toBe("Hide details");
    expect(q("[data-details]").getAttribute("aria-expanded")).toBe("true");
    q("[data-tab=plan]").click();
    expect(q("[data-panel=plan]").hidden).toBe(false);
    q("[data-tab=questions]").click();
    expect(document.activeElement).toBe(field());
    q("[data-tab=plan]").click();
    q("[data-details]").click();
    await settle(5000);
    expect(q("[data-tab=questions]").getAttribute("aria-pressed")).toBe("true");
    expect(q("[data-slot=questions]").hidden).toBe(false);
  });

  it("keeps the other cards as before: no toggle, no only-ask", async () => {
    await open(card("working"));
    expect(q("[data-details]").hidden).toBe(true);
    expect(q(".drawer").classList.contains("drawer--only-ask")).toBe(false);
  });

  it("sends all answers in one POST right after the last accept and shows the loader meanwhile", async () => {
    const c = card("needs_you");
    const gate = Promise.withResolvers<unknown>();
    await open(c, { [`POST /api/task/${c.id}/spec-answers`]: () => gate.promise });
    field().value = "IndexedDB";
    field().dispatchEvent(new Event("input"));
    expect(q(".ask-page").textContent).toBe("1 / 2");
    enter();
    await settle(0);
    expect(q(".loader").textContent).toBe("Sending 2 answers…");
    expect(posts()).toEqual(['{"answers":{"Q1":"IndexedDB","Q2":"Yes"}}']);
    gate.resolve({ ok: true, task: c });
    await settle(0);
    expect(env.stub.calls.filter((call) => call.url === `/api/task/${c.id}`).length).toBeGreaterThan(1);
    expect(localStorage).toHaveLength(0);
  });

  it("keeps the answers when the server refuses and retries from the same screen", async () => {
    const c = card("needs_you");
    await open(c, { [`POST /api/task/${c.id}/spec-answers`]: fail("Claude is busy") });
    field().value = "Mine";
    field().dispatchEvent(new Event("input"));
    enter();
    await settle(0);
    expect(q("[role=alert]").textContent).toContain("Claude is busy");
    env.stub.routes.set(`POST /api/task/${c.id}/spec-answers`, () => ({ ok: true, task: c }));
    q("[data-ask=retry]").click();
    await settle(0);
    expect(posts()).toEqual(['{"answers":{"Q1":"Mine","Q2":"Yes"}}', '{"answers":{"Q1":"Mine","Q2":"Yes"}}']);
  });

  it("explains a page without a CSRF token instead of sending", async () => {
    await open(card("needs_you"));
    document.head.replaceChildren();
    enter();
    await settle(0);
    expect(q("[role=alert]").textContent).toContain("no CSRF token");
    expect(posts()).toHaveLength(0);
  });

  it("keeps a draft across closing and reopening the drawer", async () => {
    const c = card("needs_you");
    await open(c);
    field().value = "Half typed";
    field().dispatchEvent(new Event("input"));
    env.drawer.close(false);
    await open(c);
    expect(field().value).toBe("Half typed");
  });

  it("does not refresh a task the drawer already left once the send finishes", async () => {
    const c = card("needs_you");
    const gate = Promise.withResolvers<unknown>();
    await open(c, { [`POST /api/task/${c.id}/spec-answers`]: () => gate.promise });
    enter();
    await settle(0);
    env.drawer.close(false);
    const before = env.stub.calls.length;
    gate.resolve({ ok: true, task: c });
    await settle(0);
    expect(env.stub.calls.slice(before).filter((call) => call.url.startsWith("/api/task/") && call.init?.method !== "POST")).toHaveLength(0);
    expect(makeDetail(c).questions).toHaveLength(2);
  });
});
