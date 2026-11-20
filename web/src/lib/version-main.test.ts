import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { page, watchVersion } from "@/lib/version-watch";
import { installEventSource, settle, stubFetch } from "@/test/net";

beforeEach(() => {
  vi.useFakeTimers();
  installEventSource();
  document.head.innerHTML = '<meta name="todoimpl-build" content="abc1234">';
});

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("watchVersion", () => {
  it("reloads only when the build differs from the stamped one", async () => {
    const reload = vi.fn();
    let build = "abc1234";
    stubFetch({ "GET /version": () => ({ build, version: "1" }) });
    const stop = watchVersion(reload);
    await settle(0);
    await settle(5000);
    expect(reload).not.toHaveBeenCalled();
    build = "def5678";
    await settle(5000);
    expect(reload).toHaveBeenCalledOnce();
    stop();
  });

  it("uses the first answer as baseline when the page was not stamped, and ignores errors", async () => {
    document.head.replaceChildren();
    const reload = vi.fn();
    let build = "one";
    let isDown = false;
    stubFetch({ "GET /version": () => (isDown ? new Response("x", { status: 500 }) : { build, version: "1" }) });
    const stop = watchVersion(reload);
    await settle(0);
    isDown = true;
    await settle(5000);
    isDown = false;
    await settle(5000);
    expect(reload).not.toHaveBeenCalled();
    build = "two";
    await settle(5000);
    expect(reload).toHaveBeenCalledOnce();
    stop();
  });

  it("defaults to a real page reload", async () => {
    const real = page.reload;
    expect(() => { real(); }).not.toThrow();
    const reload = vi.fn();
    page.reload = reload;
    stubFetch({ "GET /version": () => ({ build: "other", version: "1" }) });
    const stop = watchVersion();
    await settle(0);
    expect(reload).toHaveBeenCalled();
    stop();
    page.reload = real;
  });
});

describe("main", () => {
  it("registers the elements and starts the watcher", async () => {
    stubFetch({ "GET /version": () => ({ build: "abc1234", version: "1" }) });
    const { boot } = await import("@/main");
    const stop = boot();
    expect(customElements.get("ti-app")).toBeDefined();
    expect(customElements.get("ti-drawer")).toBeDefined();
    stop();
  });
});
