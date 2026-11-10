/** <ti-track>: loads at once, refetches on SSE events (debounced) and every 5 s, keeps the last data when a fetch fails. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LIVE_EVENTS } from "@/test/fixture-detail";
import { makeTrack, TRACK_ID } from "@/test/fixture-track";
import { FakeEventSource, installEventSource, lastSource, settle, stubFetch } from "@/test/net";
import { DEBOUNCE_MS, defineTrack, TiTrack, TRACK_POLL_MS } from "@/track/track";

const URL = `GET /api/umbrella/${TRACK_ID}`;
let body: () => unknown;
let calls: () => number;

function mount(): TiTrack {
  const stub = stubFetch({ [URL]: () => body() });
  calls = () => stub.calls.length;
  const view = document.createElement("ti-track") as TiTrack;
  document.body.append(view);
  return view;
}

const q = <T extends Element = HTMLElement>(view: Element, selector: string): T => {
  const found = view.querySelector<T>(selector);
  if (found === null) throw new Error(`no ${selector}`);
  return found;
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-10T12:00:00Z"));
  installEventSource();
  body = () => makeTrack();
  defineTrack();
  defineTrack();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("ti-track", () => {
  it("shows a loader naming the request, then renders the run at once", async () => {
    stubFetch({ [URL]: () => new Promise(() => {}) });
    const view = document.createElement("ti-track") as TiTrack;
    document.body.append(view);
    view.show(TRACK_ID);
    expect(q(view, ".loader").textContent).toContain(`/api/umbrella/${TRACK_ID}`);
    view.remove();
    const ready = mount();
    ready.show(TRACK_ID);
    await settle(0);
    expect(ready.querySelector(".loader")).toBeNull();
    expect(q(ready, ".t-title").textContent).toBe("Make the repos text-free (textgate-rework)");
    expect(ready.querySelectorAll(".t-kid")).toHaveLength(6);
    expect(ready.querySelectorAll(".t-round")).toHaveLength(2);
    expect(q(ready, ".t-bar")).not.toBeNull();
    expect(calls()).toBe(1);
  });

  it("opens the umbrella's live stream and refetches once for a burst of events", async () => {
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    expect(lastSource().url).toBe(`/api/live?id=${TRACK_ID}`);
    for (const event of LIVE_EVENTS) lastSource().emit(event.type, event);
    expect(calls()).toBe(1);
    await settle(DEBOUNCE_MS);
    expect(calls()).toBe(2);
    await settle(DEBOUNCE_MS * 4);
    expect(calls()).toBe(2);
  });

  it("ignores a malformed stream frame and keeps showing the run", async () => {
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    lastSource().emit("cost", "{not json");
    await settle(DEBOUNCE_MS * 2);
    expect(calls()).toBe(1);
    expect(view.querySelectorAll(".t-kid")).toHaveLength(6);
  });

  it("polls every five seconds as a fallback", async () => {
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    await settle(TRACK_POLL_MS);
    expect(calls()).toBe(2);
    await settle(TRACK_POLL_MS);
    expect(calls()).toBe(3);
  });

  it("keeps the last data, marks it stale and says why, then recovers", async () => {
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    body = () => new Response("x", { status: 500 });
    await settle(TRACK_POLL_MS);
    expect(view.hasAttribute("data-stale")).toBe(true);
    expect(q(view, "[data-stale-mark]").title).toContain("HTTP 500");
    expect(view.querySelectorAll(".t-kid")).toHaveLength(6);
    body = () => makeTrack();
    await settle(TRACK_POLL_MS);
    expect(view.hasAttribute("data-stale")).toBe(false);
    expect(view.querySelector("[data-stale-mark]")).toBeNull();
  });

  it("says so when the first load fails and keeps trying", async () => {
    body = () => new Response("x", { status: 404 });
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    expect(q(view, '[role="alert"]').textContent).toContain("HTTP 404");
    expect(view.hasAttribute("data-stale")).toBe(false);
    body = () => makeTrack();
    await settle(TRACK_POLL_MS);
    expect(view.querySelectorAll(".t-kid")).toHaveLength(6);
  });

  it("ignores an answer that arrives after a newer one", async () => {
    const answers: ((value: unknown) => void)[] = [];
    body = () => new Promise((resolve) => { answers.push(resolve); });
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    await settle(TRACK_POLL_MS);
    expect(answers).toHaveLength(1); // the poll skips while one is in flight
    lastSource().emit("cost", { cost_usd: 1, type: "cost" });
    await settle(DEBOUNCE_MS);
    expect(answers).toHaveLength(2);
    answers[1]?.(makeTrack({ title: "newer" }));
    await settle(0);
    answers[0]?.(makeTrack({ title: "older" }));
    await settle(0);
    expect(q(view, ".t-title").textContent).toBe("newer");
  });

  it("ignores an answer for a run it no longer shows", async () => {
    const answers: ((value: unknown) => void)[] = [];
    body = () => new Promise((resolve) => { answers.push(resolve); });
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    view.show(null);
    answers[0]?.(makeTrack());
    await settle(0);
    expect(view.childElementCount).toBe(0);
  });

  it("ignores a failure for a run it no longer shows", async () => {
    const answers: ((value: unknown) => void)[] = [];
    body = () => new Promise((resolve) => { answers.push(resolve); });
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    view.show("aaaa1111-2");
    answers[0]?.(new Response("x", { status: 500 }));
    await settle(0);
    expect(view.querySelector<HTMLElement>("[data-stale-mark]")?.title).not.toContain("500"); // only the new run's own 404
  });

  it("keeps expanded rows open across refetches and toggles them", async () => {
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    q<HTMLButtonElement>(view, '[data-id="2d0704cd-2"] .t-kid-main').click();
    expect(q(view, '[data-id="2d0704cd-2"]').dataset.open).toBe("true");
    await settle(TRACK_POLL_MS);
    expect(q(view, '[data-id="2d0704cd-2"]').dataset.open).toBe("true");
    q<HTMLButtonElement>(view, '[data-id="2d0704cd-2"] .t-kid-main').click();
    expect(q(view, '[data-id="2d0704cd-2"]').dataset.open).toBe("false");
    q<HTMLButtonElement>(view, ".t-group-main").click();
    expect(q(view, ".t-lines").textContent).toContain("permission");
  });

  it("keeps the round strip where it was scrolled", async () => {
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    q(view, ".t-strip").scrollLeft = 40;
    await settle(TRACK_POLL_MS);
    expect(q(view, ".t-strip").scrollLeft).toBe(40);
  });

  it("leaves out rounds and issues when there are none", async () => {
    const base = makeTrack();
    body = () => makeTrack({ counts: { ...base.counts, issues: 0 }, issues: { groups: [], total: 0 }, round: null, rounds: [] });
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    expect(view.querySelector(".t-rounds")).toBeNull();
    expect(view.querySelector(".t-issues")).toBeNull();
  });

  it("tells the app to close when Back is pressed", async () => {
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    const closed = vi.fn();
    view.addEventListener("track-close", closed);
    q<HTMLButtonElement>(view, "[data-close]").click();
    expect(closed).toHaveBeenCalledTimes(1);
  });

  it("does nothing for the same id, switches for another, and stops for null", async () => {
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    view.show(TRACK_ID);
    expect(FakeEventSource.instances).toHaveLength(1);
    view.show("aaaa1111-3");
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[0]?.closed).toBe(true);
    expect(q(view, ".t-title").textContent).toBe("aaaa1111-3");
    view.show(null);
    expect(FakeEventSource.instances[1]?.closed).toBe(true);
    expect(view.childElementCount).toBe(0);
  });

  it("stops polling and the stream when it leaves the page", async () => {
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    lastSource().emit("cost", { cost_usd: 1, type: "cost" });
    view.remove();
    await settle(TRACK_POLL_MS * 2);
    expect(calls()).toBe(1);
    expect(lastSource().closed).toBe(true);
  });

  it("ignores a refetch scheduled for a view that has gone", async () => {
    const view = mount();
    view.show(TRACK_ID);
    await settle(0);
    lastSource().emit("cost", { cost_usd: 1, type: "cost" });
    view.show(null);
    await settle(DEBOUNCE_MS * 2);
    expect(calls()).toBe(1);
  });
});
