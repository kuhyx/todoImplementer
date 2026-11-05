import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { readMeta, restoreInputs, snapshotInputs } from "@/lib/boot";
import { must } from "@/lib/dom";
import { openLive } from "@/lib/live-feed";
import { poll } from "@/lib/poller";
import { LIVE_EVENTS } from "@/test/fixture-detail";
import { installEventSource, lastSource, settle } from "@/test/net";

beforeEach(() => {
  vi.useFakeTimers();
  installEventSource();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe("openLive", () => {
  const setup = () => {
    const handlers = { onBad: vi.fn(), onEvent: vi.fn(), onState: vi.fn() };
    const stop = openLive("17a1b2c3-0", handlers);
    return { handlers, source: lastSource(), stop };
  };

  it("opens the right url and reports states", () => {
    const { handlers, source } = setup();
    expect(source.url).toBe("/api/live?id=17a1b2c3-0");
    source.emit("open");
    source.readyState = 0;
    source.emit("error");
    source.readyState = 2;
    source.emit("error");
    expect(handlers.onState.mock.calls.map((call: unknown[]) => call[0])).toEqual(["connecting", "live", "reconnecting", "closed"]);
  });

  it("delivers valid events and reports bad ones", () => {
    const { handlers, source } = setup();
    for (const event of LIVE_EVENTS) source.emit(event.type, event);
    expect(handlers.onEvent).toHaveBeenCalledTimes(LIVE_EVENTS.length);
    source.emit("activity", "not json");
    source.emit("activity", { type: "activity" });
    expect(handlers.onBad.mock.calls).toEqual([["live activity: not JSON"], [expect.stringMatching(/^live activity: at: /)]]);
  });

  it("closes itself on done and on stop", () => {
    const { handlers, source, stop } = setup();
    source.emit("done", { status: "done", type: "done" });
    expect(source.closed).toBe(true);
    expect(handlers.onState).toHaveBeenLastCalledWith("closed");
    stop();
  });
});

describe("poll", () => {
  it("runs now, then every interval, and stops", async () => {
    const task = vi.fn(() => Promise.resolve());
    const stop = poll(task, 1000);
    await settle(0);
    expect(task).toHaveBeenCalledTimes(1);
    await settle(2100);
    expect(task).toHaveBeenCalledTimes(3);
    stop();
    await settle(5000);
    expect(task).toHaveBeenCalledTimes(3);
  });

  it("skips hidden ticks and refreshes at once when visible again", async () => {
    const task = vi.fn(() => Promise.resolve());
    const isHidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    const stop = poll(task, 1000);
    await settle(3000);
    expect(task).not.toHaveBeenCalled();
    isHidden.mockReturnValue(false);
    document.dispatchEvent(new Event("visibilitychange"));
    await settle(0);
    expect(task).toHaveBeenCalledTimes(1);
    isHidden.mockReturnValue(true);
    document.dispatchEvent(new Event("visibilitychange"));
    await settle(0);
    expect(task).toHaveBeenCalledTimes(1);
    stop();
  });

  it("never overlaps itself and survives a failing task", async () => {
    const gate = Promise.withResolvers<undefined>();
    const task = vi.fn(async () => { await gate.promise; });
    const stop = poll(task, 100);
    await settle(0);
    document.dispatchEvent(new Event("visibilitychange"));
    await settle(500);
    expect(task).toHaveBeenCalledTimes(1);
    gate.resolve(undefined);
    await settle(0);
    stop();
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});
    const failing = vi.fn(() => Promise.reject(new Error("x")));
    const stop2 = poll(failing, 100);
    await settle(350);
    stop2();
    expect(failing.mock.calls.length).toBeGreaterThan(2);
    expect(logged).toHaveBeenCalled();
  });
});

describe("boot helpers", () => {
  it("treats empty and unreplaced placeholders as missing", () => {
    document.head.innerHTML = '<meta name="a" content="real"><meta name="b" content="__X__"><meta name="c" content="">';
    expect(readMeta("a")).toBe("real");
    expect(readMeta("b")).toBeNull();
    expect(readMeta("c")).toBeNull();
    expect(readMeta("zzz")).toBeNull();
    document.head.replaceChildren();
  });

  it("keeps typed text and focus across a re-render", () => {
    const root = document.createElement("div");
    document.body.append(root);
    const markup = (last: string) => `<textarea data-keep name="a"></textarea><input data-keep name="b"><input name="${last}">`;
    root.innerHTML = markup("plain");
    const [a, b, plain] = root.querySelectorAll("textarea, input") as unknown as HTMLInputElement[];
    if (a === undefined || b === undefined || plain === undefined) throw new Error("fixture");
    a.value = "typed";
    b.focus();
    const snapshot = snapshotInputs(root);
    expect(snapshot.focus).toBe("b");
    root.innerHTML = markup("new");
    restoreInputs(root, snapshot);
    expect(must<HTMLInputElement>(root, "[name=a]").value).toBe("typed");
    expect(document.activeElement).toBe(root.querySelector("[name=b]"));
    expect(plain.isConnected).toBe(false);
    root.querySelector<HTMLInputElement>("input[name=new]")?.focus();
    expect(snapshotInputs(root).focus).toBeNull();
    must<HTMLInputElement>(root, "[name=a]").focus();
    expect(snapshotInputs(document.createElement("div")).focus).toBeNull();
    root.querySelector("input[name=new]")?.setAttribute("data-keep", "");
    root.querySelector<HTMLInputElement>("input[name=new]")?.focus();
    expect(snapshotInputs(root).focus).toBe("new");
    const button = document.createElement("button");
    root.append(button);
    button.focus();
    expect(snapshotInputs(root).focus).toBeNull();
  });
});
