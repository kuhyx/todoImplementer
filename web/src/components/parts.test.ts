import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Action } from "@/lib/schemas-common";

import { idleBar, pendingLoader, renderAction, slowTimer } from "@/components/action-bar";
import { createFeed, FEED_CAP } from "@/components/feed-view";
import { loader, showToast } from "@/components/feedback";
import { NOW } from "@/test/fixtures";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
});

describe("feedback", () => {
  it("names what it waits on", () => {
    expect(loader("Loading x").textContent).toBe("Loading x");
    expect(loader("a").getAttribute("role")).toBe("status");
  });

  it("toasts disappear on click and on time, errors last longer", () => {
    showToast("hello");
    showToast("bad", "error");
    const region = document.querySelector("#toasts");
    expect(region?.children).toHaveLength(2);
    expect(region?.querySelector('[role="alert"]')?.textContent).toBe("bad");
    region?.querySelector<HTMLElement>(".toast-info")?.click();
    expect(region?.children).toHaveLength(1);
    vi.advanceTimersByTime(5000);
    expect(region?.children).toHaveLength(1);
    vi.advanceTimersByTime(8000);
    expect(region?.children).toHaveLength(0);
    showToast("again");
    expect(document.querySelectorAll(".toasts")).toHaveLength(1);
    vi.advanceTimersByTime(5000);
  });
});

describe("renderAction", () => {
  const ship: Action = { confirm: true, enabled: true, id: "ship", label: "Ship", reason: null };
  const off: Action = { enabled: false, id: "start", label: "Start", reason: "3 runs are already going" };
  const host = (state = idleBar()) => ({ activate: vi.fn(), cancelConfirm: vi.fn(), state: () => state });

  it("renders an enabled action that activates on click", () => {
    const h = host();
    const element = renderAction(ship, h, "t1");
    element.querySelector("button")?.click();
    expect(h.activate).toHaveBeenCalledWith(ship);
    expect(element.querySelector("button")?.className).toContain("primary");
  });

  it("keeps a disabled action visible with its reason and does nothing on click", () => {
    const h = host();
    const element = renderAction(off, h, "t1");
    const button = element.querySelector("button");
    button?.click();
    expect(h.activate).not.toHaveBeenCalled();
    expect(button?.getAttribute("aria-disabled")).toBe("true");
    expect(element.querySelector(".reason")?.textContent).toBe("3 runs are already going");
    expect(button?.getAttribute("aria-describedby")).toBe(element.querySelector(".reason")?.id);
  });

  it("falls back to an empty reason string and blocks other actions while one is pending", () => {
    const h = host({ confirming: null, pending: "cancel", slow: false });
    const element = renderAction({ ...off, reason: null }, h, "t1");
    expect(element.querySelector(".reason")?.textContent).toBe("");
    const other = renderAction({ enabled: true, id: "send", label: "Send", reason: null }, h, "t1");
    expect(other.querySelector("button")?.getAttribute("aria-disabled")).toBe("true");
    other.querySelector("button")?.click();
    expect(h.activate).not.toHaveBeenCalled();
  });

  it("shows the busy state with the label", () => {
    const element = renderAction(ship, host({ confirming: null, pending: "ship", slow: false }), "t1");
    expect(element.querySelector("button")?.getAttribute("aria-busy")).toBe("true");
    expect(element.querySelector("button")?.textContent).toBe("Ship…");
  });

  it("asks before a confirm action and can back out", () => {
    const h = host({ confirming: "ship", pending: null, slow: false });
    const element = renderAction(ship, h, "t1");
    expect(element.textContent).toContain("Ship: are you sure?");
    element.querySelector<HTMLElement>("[data-confirm]")?.click();
    expect(h.activate).toHaveBeenCalledWith(ship);
    [...element.querySelectorAll("button")].find((b) => b.textContent === "Back")?.click();
    expect(h.cancelConfirm).toHaveBeenCalled();
  });

  it("shows a loader naming the wait only once it is slow", () => {
    expect(pendingLoader(ship, "t1", idleBar())).toBeNull();
    expect(pendingLoader(ship, "t1", { confirming: null, pending: "ship", slow: false })).toBeNull();
    expect(pendingLoader(ship, "t1", { confirming: null, pending: "ship", slow: true })?.textContent).toBe("Waiting for the server to finish: Ship (task t1)");
    expect(pendingLoader(undefined, "t1", { confirming: null, pending: "ship", slow: true })?.textContent).toContain("ship");
  });

  it("fires the slow timer after 1 s and can be cancelled", () => {
    const onSlow = vi.fn();
    const stop = slowTimer(onSlow);
    vi.advanceTimersByTime(999);
    expect(onSlow).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onSlow).toHaveBeenCalledOnce();
    const never = vi.fn();
    slowTimer(never)();
    vi.advanceTimersByTime(5000);
    expect(never).not.toHaveBeenCalled();
    stop();
  });
});

describe("feed", () => {
  const event = (seq: number, text = "line") => ({ at: NOW, kind: "tool" as const, seq, text, tool: "Bash", type: "activity" as const });

  it("appends, dedupes replays, labels tools and shows state", () => {
    const feed = createFeed();
    document.body.append(feed.el);
    expect(feed.el.querySelector(".empty")?.hasAttribute("hidden")).toBe(false);
    feed.append(event(1));
    feed.append(event(1));
    feed.append({ ...event(2), kind: "text", tool: null });
    expect(feed.el.querySelectorAll(".feed-item")).toHaveLength(2);
    expect(feed.el.querySelector(".feed-kind")?.textContent).toBe("tool: Bash");
    expect(feed.el.querySelectorAll(".feed-kind")[1]?.textContent).toBe("text");
    expect(feed.el.querySelector(".empty")?.hasAttribute("hidden")).toBe(true);
    feed.setState("reconnecting");
    expect(feed.el.querySelector(".feed-state")?.textContent).toBe("connection lost, reconnecting…");
  });

  it("collapses long text and caps the list", () => {
    const feed = createFeed();
    feed.append(event(1, "x".repeat(900)));
    expect(feed.el.querySelector("details summary")?.textContent).toContain("(900 characters)");
    for (let seq = 2; seq <= FEED_CAP + 5; seq += 1) feed.append(event(seq));
    expect(feed.el.querySelectorAll(".feed-item")).toHaveLength(FEED_CAP);
  });

  it("keeps the scroll position when the user scrolled up", () => {
    const feed = createFeed();
    const scroller = feed.el.querySelector<HTMLElement>(".feed-scroll");
    if (scroller === null) throw new Error("scroller");
    Object.defineProperties(scroller, {
      clientHeight: { configurable: true, value: 100 },
      scrollHeight: { configurable: true, value: 1000 },
    });
    scroller.scrollTop = 0;
    feed.append(event(1));
    expect(scroller.scrollTop).toBe(0);
    scroller.scrollTop = 900;
    feed.append(event(2));
    expect(scroller.scrollTop).toBe(1000);
  });
});
