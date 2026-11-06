import { describe, expect, it, vi } from "vitest";

import { card, env, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { LIVE_EVENTS, makeDetail } from "@/test/fixture-detail";
import { lastSource, settle, stubFetch } from "@/test/net";

useDrawerHarness();

describe("opening", () => {
  it("shows a loader naming the request at once, then the task", async () => {
    const c = card("working");
    env.stub = stubFetch({ [`GET /api/task/${c.id}`]: () => makeDetail(c) });
    env.drawer.open(c.id);
    expect(q("[data-slot=head]").textContent).toBe(`Loading task ${c.id} from /api/task/${c.id}…`);
    await settle(0);
    expect(q("#drawer-title").textContent).toBe(c.title);
    expect(q("[data-slot=actions]").textContent).toContain("Cancel run");
    expect(q("[data-slot=send]").hidden).toBe(false);
    expect(lastSource().url).toBe(`/api/live?id=${c.id}`);
  });

  it("shows an error banner when the task cannot be loaded", async () => {
    stubFetch({ "GET /api/task/17a1b2c3-0": new Response("x", { status: 500 }) });
    env.drawer.open("17a1b2c3-0");
    await settle(0);
    expect(q("[data-slot=head]").textContent).toBe("Cannot load task 17a1b2c3-0: /api/task/17a1b2c3-0: HTTP 500");
    stubFetch({ "GET /api/task/17a1b2c3-0": new Response("x", { status: 500 }) });
    await settle(5000);
  });

  it("ignores a response that arrives after another task was opened", async () => {
    const a = card("working");
    const b = card("needs_you");
    const gate = Promise.withResolvers<unknown>();
    stubFetch({
      [`GET /api/task/${a.id}`]: () => gate.promise,
      [`GET /api/task/${b.id}`]: () => makeDetail(b),
    });
    env.drawer.open(a.id);
    await settle(0);
    env.drawer.open(b.id);
    await settle(0);
    gate.resolve(makeDetail(a));
    await settle(0);
    expect(q("#drawer-title").textContent).toBe(b.title);
    env.drawer.close();
    stubFetch({ [`GET /api/task/${a.id}`]: new Response("x", { status: 500 }) });
    env.drawer.open(a.id);
    env.drawer.close(false);
    await settle(0);
  });

  it("closes with Close, Escape and the scrim, returning focus to the opener", async () => {
    const onClose = vi.fn();
    env.drawer.addEventListener("drawer-close", onClose);
    await open(card("working"));
    q("#opener").blur();
    q(".drawer-bar .btn:last-child").click();
    expect(env.drawer.hidden).toBe(true);
    expect(document.activeElement).toBe(q("#opener"));
    await open(card("working"));
    q(".drawer").dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Escape" }));
    await open(card("working"));
    q(".scrim").click();
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("traps Tab inside the drawer", async () => {
    await open(card("working"));
    const buttons = [...env.drawer.querySelectorAll<HTMLElement>("button, textarea, summary")].filter((item) => item.getAttribute("aria-disabled") !== "true" && !item.hidden);
    const first = buttons[0];
    const last = buttons.at(-1);
    last?.focus();
    const forward = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Tab" });
    q(".drawer").dispatchEvent(forward);
    expect(forward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(first);
    const back = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Tab", shiftKey: true });
    q(".drawer").dispatchEvent(back);
    expect(document.activeElement).toBe(last);
    const middle = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Tab" });
    buttons[1]?.focus();
    q(".drawer").dispatchEvent(middle);
    expect(middle.defaultPrevented).toBe(false);
    q(".drawer").dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "a" }));
  });

  it("switches tabs and counts diff files and checks", async () => {
    await open(card("working"));
    expect(q("[data-tab=diff]").textContent).toBe("Diff (1)");
    expect(q("[data-tab=live]").textContent).toBe("Live check (2)");
    expect(q("[data-tab=checks]").textContent).toBe("Checks (2)");
    expect(q("[data-tab=plan]").textContent).toBe("Plan");
    q("[data-tab=plan]").click();
    expect(q("[data-panel=plan]").hidden).toBe(false);
    expect(q("[data-panel=activity]").hidden).toBe(true);
    expect(q("[data-tab=plan]").getAttribute("aria-pressed")).toBe("true");
  });
});

describe("live stream", () => {
  it("appends activity, merges stage and cost, and refreshes on stage and done", async () => {
    const c = card("working");
    await open(c);
    const source = lastSource();
    const changed = vi.fn();
    env.drawer.addEventListener("task-changed", changed);
    source.emit("open");
    for (const event of LIVE_EVENTS.slice(1, 4)) source.emit(event.type, event);
    expect(env.drawer.querySelectorAll(".feed-item")).toHaveLength(3);
    expect(q(".feed-state").textContent).toBe("live");
    source.emit("stage", { ...LIVE_EVENTS[0], actions: [], current: "checks running", status: "working" });
    expect(q(".drawer-current").textContent).toBe("checks running");
    expect(q("[data-slot=send]").hidden).toBe(true);
    source.emit("cost", { cost_usd: 9.5, type: "cost" });
    expect(changed).toHaveBeenCalledTimes(1);
    source.emit("done", { status: "ready_to_ship", type: "done" });
    expect(changed).toHaveBeenCalledTimes(2);
    expect(q(".feed-state").textContent).toBe("stream ended");
  });

  it("ignores stage and cost before the task has loaded and reports bad payloads", async () => {
    const c = card("working");
    stubFetch({ [`GET /api/task/${c.id}`]: () => new Promise(() => {}) });
    env.drawer.open(c.id);
    const source = lastSource();
    source.emit("stage", LIVE_EVENTS[0]);
    source.emit("cost", { cost_usd: 1, type: "cost" });
    source.emit("activity", "junk");
    expect(document.querySelector("#toasts")?.textContent).toContain("live activity: not JSON");
  });
});

