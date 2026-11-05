import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError, filterQuery, getJson, loadAb, loadAnomalies, loadContext, loadEfficiency, loadFile, loadGeneric, loadIndex, loadItems, loadLevers,
  loadOverview, loadSession, loadSessions,
} from "@/usage/api";
import { fakeFetch, fixtures } from "@/usage/fixtures/load";
import { sessionsPanel } from "@/usage/schemas";

const stub = (response: () => Promise<Response>): void => {
  vi.stubGlobal("fetch", vi.fn(response));
};
const urls = (): string[] => vi.mocked(fetch).mock.calls.map(([url]) => (url as string));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getJson", () => {
  it("parses a good body", async () => {
    stub(() => Promise.resolve(Response.json(fixtures.sessions)));
    const body = await getJson("/x", sessionsPanel);
    expect(body.sessions).toHaveLength(42);
  });

  it("names the URL on a network failure, an HTTP error, bad JSON and a wrong shape", async () => {
    stub(() => Promise.reject(new TypeError("boom")));
    await expect(getJson("/x", sessionsPanel)).rejects.toThrow("/x: cannot reach the server");
    stub(() => Promise.resolve(new Response("{}", { status: 503 })));
    await expect(getJson("/x", sessionsPanel)).rejects.toMatchObject({ message: "/x: HTTP 503", status: 503 });
    stub(() => Promise.resolve(new Response("<html>")));
    await expect(getJson("/x", sessionsPanel)).rejects.toThrow("not JSON");
    stub(() => Promise.resolve(new Response('{"sessions":[{"key":1}]}')));
    await expect(getJson("/x", sessionsPanel)).rejects.toThrow("unexpected shape at sessions.0.active_s");
    stub(() => Promise.resolve(new Response("[]")));
    await expect(getJson("/x", sessionsPanel)).rejects.toThrow("unexpected shape at root");
  });

  it("rethrows an abort untouched", async () => {
    const controller = new AbortController();
    controller.abort();
    stub(() => Promise.reject(new DOMException("aborted", "AbortError")));
    await expect(getJson("/x", sessionsPanel, controller.signal)).rejects.not.toBeInstanceOf(ApiError);
  });
});

describe("filterQuery", () => {
  it("keeps the six global filters, drops scope=all and everything else", () => {
    const query = filterQuery(new URLSearchParams("cwd=a&scope=all&model=m&from=2026-01-01&to=2026-02-01&window=w&t.sessions.q=x&zzz=1"));
    expect(query.toString()).toBe("cwd=a&from=2026-01-01&model=m&to=2026-02-01&window=w");
    expect(filterQuery(new URLSearchParams("scope=main")).get("scope")).toBe("main");
  });
});

describe("loaders", () => {
  it("hit the documented URLs and parse every fixture", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeFetch()));
    const none = new URLSearchParams("cwd=%2Fhome%2Fx&t.sessions.q=ignored");
    await Promise.all([loadAb(none), loadAnomalies(none), loadContext(none), loadEfficiency(none), loadLevers(none), loadOverview(none), loadSessions(none)]);
    const [index, hooks, items, session, file] = await Promise.all([loadIndex(), loadGeneric("hooks")(none), loadItems(new URLSearchParams("model=m")), loadSession("a b"), loadFile("/a/b.md")]);
    expect(index.panels.length).toBeGreaterThan(20);
    expect(hooks.hooks).toBeDefined();
    expect(items.items).toHaveLength(7);
    expect(session.session.key).toBeTruthy();
    expect(file.path).toBe("/home/kuhy/.claude/memories/mistakes.md");
    expect(urls()).toContain("/api/tokens/panel/sessions?cwd=%2Fhome%2Fx&t.sessions.limit=0");
    expect(urls()).toContain("/api/tokens/panel/overview?cwd=%2Fhome%2Fx&t.daily.limit=0&t.weekly.limit=0");
    expect(urls()).toContain("/api/tokens/panel/hooks?cwd=%2Fhome%2Fx");
    expect(urls()).toContain("/api/tokens/items?model=m");
    expect(urls()).toContain("/api/tokens/session/a%20b");
    expect(urls()).toContain("/api/tokens/context-file?path=%2Fa%2Fb.md");
    expect(urls()).toContain("/api/tokens");
  });

  it("send no query when there are no filters", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeFetch()));
    await loadItems(new URLSearchParams());
    await loadGeneric("hooks")(new URLSearchParams());
    expect(urls()).toEqual(["/api/tokens/items", "/api/tokens/panel/hooks"]);
  });
});
