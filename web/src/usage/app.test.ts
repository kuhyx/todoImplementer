import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { REFRESH_MS, UsageApp } from "@/usage/app";
import { boot } from "@/usage/boot";
import { fakeFetch, fixtures } from "@/usage/fixtures/load";

const settle = async (): Promise<void> => {
  await vi.advanceTimersByTimeAsync(0);
  await vi.advanceTimersByTimeAsync(0);
};
const mount = async (hash: string, routes: Record<string, unknown> = {}): Promise<UsageApp> => {
  vi.stubGlobal("fetch", vi.fn(fakeFetch(routes)));
  globalThis.location.hash = hash;
  const app = new UsageApp();
  document.body.replaceChildren(app);
  await settle();
  return app;
};
const q = (app: Element, selector: string): Element => app.querySelector(selector)!;
const tabs = (app: Element): string[] => [...app.querySelectorAll(".tabs a")].map((a) => a.textContent);

beforeEach(() => {
  vi.useFakeTimers();
  if (customElements.get("usage-app") === undefined) boot();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("usage-app", () => {
  it("opens the overview by default with every tab and the filters", async () => {
    const app = await mount("");
    expect(tabs(app)).toEqual(["Spend", "Sessions", "Per todo item", "Efficiency", "Autonomy", "Levers", "Context files", "Anomalies", "A/B", "More panels"]);
    expect(q(app, '.tabs [aria-current="page"]').textContent).toBe("Spend");
    expect(app.querySelectorAll(".filters select")).toHaveLength(4);
    expect(app.querySelectorAll(".chart svg").length).toBeGreaterThan(5);
    expect(q(app, "main").hasAttribute("aria-busy")).toBe(false);
  });

  it.each([
    ["#/sessions", "Sessions"],
    ["#/s/abc", "Cost per prompt"],
    ["#/f/%2Fa.md", "Content"],
    ["#/items", "Per repo"],
    ["#/more", "Panels without"],
    ["#/more/hooks", "hooks"],
    ["#/levers", "Levers"],
  ])("routes %s", async (hash, expected) => {
    const app = await mount(hash);
    expect(app.textContent).toContain(expected);
  });

  it("opens the session and file deep links the MCP server sends", async () => {
    const session = await mount("#/s/a56d1e9e");
    expect(session.querySelector('.tabs [aria-current="page"]')?.textContent).toBe("Sessions");
    const file = await mount("#/f/%2Fhome%2Fkuhy%2Fx.md");
    expect(file.querySelector('.tabs [aria-current="page"]')?.textContent).toBe("Context files");
  });

  it("changing a filter rewrites the hash and reloads the view with it", async () => {
    const app = await mount("#/sessions?t.sessions.q=x");
    const scope = q(app, 'select[data-filter="scope"]') as HTMLSelectElement;
    scope.value = "main";
    scope.dispatchEvent(new Event("change", { bubbles: true }));
    expect(globalThis.location.hash).toBe("#/sessions?t.sessions.q=x&scope=main");
    await settle();
    expect(vi.mocked(fetch).mock.calls.some(([url]) => (url as string).includes("scope=main"))).toBe(true);
    scope.value = "all";
    scope.dispatchEvent(new Event("change", { bubbles: true }));
    await settle();
    expect(globalThis.location.hash).toBe("#/sessions?t.sessions.q=x");
    const cwd = q(app, 'select[data-filter="cwd"]') as HTMLSelectElement;
    cwd.value = "";
    cwd.dispatchEvent(new Event("change", { bubbles: true }));
    expect(globalThis.location.hash).toBe("#/sessions?t.sessions.q=x");
  });

  it("keeps an unknown filter value from the hash selectable", async () => {
    const app = await mount("#/overview?cwd=%2Fgone");
    expect((q(app, 'select[data-filter="cwd"]') as HTMLSelectElement).value).toBe("/gone");
  });

  it("names the failing URL when the server answers badly", async () => {
    const app = await mount("#/sessions", { "/api/tokens/panel/sessions": { sessions: "no" } });
    expect(q(app, ".error").textContent).toContain("unexpected shape at sessions");
    expect(q(app, "main").hasAttribute("aria-busy")).toBe(false);
  });

  it("shows a loader that names the view while the first request is pending", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    globalThis.location.hash = "#/context";
    const app = new UsageApp();
    document.body.replaceChildren(app);
    await settle();
    expect(q(app, ".loading").textContent).toBe("Loading context…");
    expect(q(app, "main").getAttribute("aria-busy")).toBe("true");
  });

  it("refreshes the open view every minute unless the reader is typing in it", async () => {
    const app = await mount("#/sessions");
    const calls = (): number => vi.mocked(fetch).mock.calls.length;
    const before = calls();
    await vi.advanceTimersByTimeAsync(REFRESH_MS);
    expect(calls()).toBeGreaterThan(before);
    const search = q(app, "usage-table input[type=search]") as HTMLInputElement;
    search.focus();
    const typing = calls();
    await vi.advanceTimersByTimeAsync(REFRESH_MS);
    expect(calls()).toBe(typing);
  });

  it("shows no error from a request that was superseded", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeFetch()));
    await mount("#/overview");
    const late = Promise.withResolvers<Response>();
    vi.stubGlobal("fetch", vi.fn((url: string) => (url.includes("sessions") ? late.promise : fakeFetch()(url))));
    globalThis.location.hash = "#/sessions";
    document.querySelector<UsageApp>("usage-app")?.show();
    await settle();
    globalThis.location.hash = "#/levers";
    document.querySelector<UsageApp>("usage-app")?.show();
    late.reject(new Error("late failure"));
    await settle();
    expect(document.querySelector(".error")).toBeNull();
  });

  it("ignores a result that arrives after the reader moved on, and stops timers when removed", async () => {
    const app = await mount("#/sessions");
    globalThis.location.hash = "#/levers";
    app.show();
    globalThis.location.hash = "#/ab";
    app.show();
    await settle();
    expect(app.textContent).toContain("Judgment agents");
    app.remove();
    const before = vi.mocked(fetch).mock.calls.length;
    await vi.advanceTimersByTimeAsync(REFRESH_MS * 2);
    expect(vi.mocked(fetch).mock.calls).toHaveLength(before);
    expect(fixtures.index.panels.length).toBeGreaterThan(0);
  });

  it("boot registers the elements once and returns the version watcher's stop function", () => {
    vi.stubGlobal("fetch", vi.fn(fakeFetch()));
    const stop = boot();
    expect(customElements.get("usage-app")).toBeDefined();
    expect(customElements.get("usage-table")).toBeDefined();
    stop();
  });
});
