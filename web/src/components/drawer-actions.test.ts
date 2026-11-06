import { describe, expect, it, vi } from "vitest";

import { card, env, fail, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { freeDetail } from "@/test/fixture-ask";
import { makeDetail } from "@/test/fixture-detail";
import { preset } from "@/test/fixture-presets";
import { settle, stubFetch } from "@/test/net";

useDrawerHarness();

describe("actions", () => {
  it("renders every server action and disables with the reason", async () => {
    const c = { ...card("backlog"), actions: [{ enabled: false, id: "start" as const, label: "Start", reason: "3 runs are already going" }] };
    await open(c);
    expect(q("[data-slot=actions]").textContent).toContain("3 runs are already going");
    q("[data-action=start]").click();
    expect(env.stub.calls.filter((call) => call.init?.method === "POST")).toHaveLength(0);
  });

  it("confirm -> pending in the same tick -> loader after 1 s -> server truth", async () => {
    const c = card("ready_to_ship");
    const done = { ...c,  actions: [], column: "done" as const, status: "done" as const  };
    let state = c;
    await open(c, {
      [`GET /api/task/${c.id}`]: () => makeDetail(state),
      [`POST /api/task/${c.id}/ship`]: async () => {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        state = done;
        return { ok: true, task: done };
      },
    });
    const changed = vi.fn();
    env.drawer.addEventListener("task-changed", changed);
    q("[data-action=ship]").click();
    expect(q("[data-slot=actions]").textContent).toContain("Ship: are you sure?");
    expect(document.activeElement).toBe(q("[data-confirm]"));
    q("[data-confirm]").click();
    expect(q("[data-action=ship]").getAttribute("aria-busy")).toBe("true");
    expect(q("[data-slot=pending]").textContent).toBe("");
    await settle(1000);
    expect(q("[data-slot=pending]").textContent).toBe(`Waiting for the server to finish: Ship (task ${c.id})`);
    await settle(600);
    expect(q(".drawer-chips .chip").textContent).toBe("Done");
    expect(changed).toHaveBeenCalled();
    expect(document.querySelector("#toasts")?.textContent).toContain("Ship: done");
    const post = env.stub.calls.find((call) => call.init?.method === "POST");
    expect(post?.init?.headers).toMatchObject({ "X-Todoimpl-Token": "tok123" });
  });

  it("Escape in the confirm step backs out without closing", async () => {
    const c = card("ready_to_ship");
    await open(c);
    q("[data-action=ship]").click();
    q(".drawer").dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Escape" }));
    expect(env.drawer.hidden).toBe(false);
    expect(q("[data-slot=actions]").textContent).not.toContain("are you sure");
    q("[data-action=ship]").click();
    q(".confirm .btn:not(.primary)").click();
    expect(q("[data-slot=actions]").textContent).not.toContain("are you sure");
  });

  it("shows the server's own error text and refreshes", async () => {
    const c = card("working");
    await open(c, { [`POST /api/task/${c.id}/cancel`]: fail("Already finished") });
    q("[data-action=cancel]").click();
    q("[data-confirm]").click();
    await settle(0);
    expect(document.querySelector('#toasts [role="alert"]')?.textContent).toBe("Already finished");
    expect(q("[data-action=cancel]").getAttribute("aria-busy")).toBe("false");
  });

  it("falls back to a generic message for a non-API failure", async () => {
    const c = card("backlog");
    await open(c, { [`POST /api/task/${c.id}/start`]: () => { throw new TypeError("x"); } });
    q("[data-action=start]").click();
    await settle(0);
    expect(document.querySelector("#toasts")?.textContent).toContain("/start: cannot reach the server");
  });

  it("refuses to POST without a stamped CSRF token", async () => {
    document.head.innerHTML = '<meta name="todoimpl-csrf" content="__TODOIMPL_CSRF__">';
    const c = card("backlog");
    await open(c);
    q("[data-action=start]").click();
    expect(document.querySelector("#toasts")?.textContent).toContain("no CSRF token");
    expect(env.stub.calls.filter((call) => call.init?.method === "POST")).toHaveLength(0);
  });

  it("copy-resume copies the value and falls back to showing the command", async () => {
    const c = card("working");
    await open(c);
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    q("[data-action=copy-resume]").click();
    await settle(0);
    expect(writeText).toHaveBeenCalledWith("cd /tmp/wt && claude --resume 0b1c2d3e");
    expect(document.querySelector("#toasts")?.textContent).toContain("Command copied");
    vi.stubGlobal("navigator", { clipboard: { writeText: () => Promise.reject(new Error("denied")) } });
    q("[data-action=copy-resume]").click();
    await settle(0);
    expect(document.querySelector("#toasts")?.textContent).toContain("Copy was blocked here. Command: cd /tmp/wt");
  });

  it("[T1681] copy-fix copies the permission command and go posts to /go", async () => {
    const copy = { enabled: true, id: "copy-fix" as const, label: "Copy", reason: null, value: "cd /w && sudo true" };
    const c = { ...card("working"), actions: [{ enabled: true, id: "go" as const, label: "Go", reason: null }, copy] };
    await open(c, { [`POST /api/task/${c.id}/go`]: () => ({ ok: true, task: c }) });
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    q("[data-action=copy-fix]").click();
    await settle(0);
    expect(writeText).toHaveBeenCalledWith("cd /w && sudo true");
    q("[data-action=go]").click();
    await settle(0);
    expect(env.stub.calls.some((call) => call.init?.method === "POST" && call.url.endsWith("/go"))).toBe(true);
  });

  it("copy-resume without any command says so", async () => {
    const c = { ...card("working"), actions: [{ enabled: true, id: "copy-resume" as const, label: "Copy", reason: null }] };
    await open(c, { [`GET /api/task/${c.id}`]: () => ({ ...makeDetail(c), resume_command: null }) });
    q("[data-action=copy-resume]").click();
    await settle(0);
    expect(document.querySelector("#toasts")?.textContent).toContain("There is no resume command yet.");
  });

  it("a slow action finishing after the drawer closed does not touch the page", async () => {
    const c = card("backlog");
    await open(c, { [`POST /api/task/${c.id}/start`]: async () => { await new Promise((r) => setTimeout(r, 3000)); return { ok: true, task: c }; } });
    q("[data-action=start]").click();
    env.drawer.close();
    await settle(3500);
    expect(env.drawer.hidden).toBe(true);
    expect(env.drawer.children).toHaveLength(0);
  });

  it("copy-resume uses the detail's command when the action has no value", async () => {
    const c = { ...card("working"), actions: [{ enabled: true, id: "copy-resume" as const, label: "Copy", reason: null }] };
    await open(c);
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    q("[data-action=copy-resume]").click();
    await settle(0);
    expect(writeText).toHaveBeenCalledWith(`cd /tmp/wt/${c.id} && claude --resume 0b1c2d3e`);
    const bare = { ...c, id: "99a1b2c3-0" };
    env.drawer.open(bare.id);
    stubFetch({ [`GET /api/task/${bare.id}`]: () => ({ ...makeDetail(bare), resume_command: null }) });
  });
});

describe("send and spec answers", () => {
  it("sends the message, clears the box, and keeps typing across refreshes", async () => {
    const c = card("working");
    await open(c, { [`POST /api/task/${c.id}/send`]: { ok: true, task: c } });
    const box = q<HTMLTextAreaElement>("textarea[name=send]");
    q("[data-action=send]").click();
    expect(document.querySelector("#toasts")?.textContent).toContain("Write a message first.");
    box.value = "use the other port";
    await settle(5000);
    expect(q<HTMLTextAreaElement>("textarea[name=send]").value).toBe("use the other port");
    box.dispatchEvent(new KeyboardEvent("keydown", { ctrlKey: true, key: "Enter" }));
    box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
    await settle(0);
    const post = env.stub.calls.find((call) => call.init?.method === "POST");
    expect(post?.init?.body).toBe('{"text":"use the other port"}');
    expect(box.value).toBe("");
  });

  it("answers a plain Claude question from the card's own box and clears it", async () => {
    const c = freeDetail().card;
    await open(c, { [`GET /api/task/${c.id}`]: freeDetail(), [`POST /api/task/${c.id}/send`]: { ok: true, task: c } });
    expect(q("[data-slot=send]").hidden).toBe(true);
    expect(q(".drawer").classList.contains("drawer--ask")).toBe(true);
    const box = q<HTMLTextAreaElement>("textarea[name=ask-send]");
    q("[data-action=send]").click();
    expect(document.querySelector("#toasts")?.textContent).toContain("Write a message first.");
    box.value = "use port 8790";
    q("[data-action=send]").click();
    await settle(0);
    const post = env.stub.calls.find((call) => call.init?.method === "POST");
    expect(post?.init?.body).toBe('{"text":"use port 8790"}');
    expect(q<HTMLTextAreaElement>("textarea[name=ask-send]").value).toBe("");
  });

  it("switches to Questions once and back to Activity when they are answered", async () => {
    const c = card("needs_you");
    await open(c);
    expect(q("[data-tab=questions]").getAttribute("aria-pressed")).toBe("true");
    expect(q("[data-slot=questions]").hidden).toBe(false);
    q("[data-details]").click();
    q("[data-tab=plan]").click();
    await settle(5000);
    expect(q("[data-tab=plan]").getAttribute("aria-pressed")).toBe("true");
    expect(q("[data-slot=questions]").hidden).toBe(true);
    expect(q(".drawer").classList.contains("drawer--ask")).toBe(false);
    q("[data-tab=questions]").click();
    const working = { ...makeDetail(c), card: { ...c, ...preset("working", true) } };
    env.stub.routes.set(`GET /api/task/${c.id}`, () => working);
    await settle(5000);
    expect(q("[data-tab=activity]").getAttribute("aria-pressed")).toBe("true");
    expect(q("[data-slot=questions]").hidden).toBe(true);
  });

  it("approves the drafted lesson by id", async () => {
    const c = card("ready_to_ship");
    await open(c, { [`POST /api/task/${c.id}/lesson-approve`]: { ok: true, task: c } });
    q("[data-action=lesson-approve]").click();
    await settle(0);
    const post = env.stub.calls.find((call) => call.init?.method === "POST");
    expect(post?.init?.body).toBe('{"lesson_id":"l1"}');
  });

  it("sends an empty lesson id when no lesson exists", async () => {
    const c = { ...card("working"), actions: [{ enabled: true, id: "lesson-approve" as const, label: "Approve", reason: null }] };
    await open(c, { [`POST /api/task/${c.id}/lesson-approve`]: { ok: true, task: c } });
    q("[data-action=lesson-approve]").click();
    await settle(0);
    expect(env.stub.calls.find((call) => call.init?.method === "POST")?.init?.body).toBe('{"lesson_id":""}');
  });
});
