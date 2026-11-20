import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BOARD_POLL_MS, defineApp, TiApp, USAGE_POLL_MS } from "@/components/app";
import { defineDrawer } from "@/components/drawer";
import { makeDetail, makeUsage } from "@/test/fixture-detail";
import { makeBoard, makeCards } from "@/test/fixtures";
import { type FetchStub, installEventSource, settle, stubFetch } from "@/test/net";

const q = <T extends Element = HTMLElement>(sel: string): T => {
  const element = document.querySelector<T>(sel);
  if (element === null) throw new Error(`no ${sel}`);
  return element;
};
const READY = "20a1b2c3-0";
let stub: FetchStub;
let boardBody: () => unknown;

async function mountApp(hash = ""): Promise<TiApp> {
  history.replaceState(null, "", `/${hash}`);
  boardBody = () => makeBoard();
  stub = stubFetch({
    [`GET /api/task/${READY}`]: () => makeDetail(makeCards().find((c) => c.id === READY)!),
    "GET /api/board": () => boardBody(),
    "GET /api/usage": () => makeUsage(),
  });
  const app = new TiApp();
  document.body.append(app);
  await settle(0);
  return app;
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-26T06:00:00Z"));
  installEventSource();
  document.head.innerHTML = '<meta name="todoimpl-build" content="abc1234"><meta name="todoimpl-csrf" content="tok">';
  document.body.replaceChildren();
  defineDrawer();
  defineApp();
  defineApp();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  history.replaceState(null, "", "/");
});

describe("ti-app", () => {
  it("shows a loader naming the board request until data arrives, then the board", async () => {
    history.replaceState(null, "", "/");
    stubFetch({ "GET /api/board": () => new Promise(() => {}), "GET /api/usage": () => makeUsage() });
    const app = document.createElement("ti-app");
    document.body.append(app);
    expect(q(".board-host").textContent).toBe("Loading the board from /api/board…");
    expect(q(".toolbar").hidden).toBe(true);
    globalThis.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(q(".toolbar").hidden).toBe(true);
    app.remove();
    await mountApp();
    expect(document.querySelectorAll(".col")).toHaveLength(4);
    expect(q(".toolbar").hidden).toBe(false);
    expect(q(".usage").textContent).toContain("Today $12.37");
    expect(q(".usage").textContent).toContain("abc1234");
  });

  it("keeps the last board and says so when a poll fails, then recovers", async () => {
    await mountApp();
    boardBody = () => { throw new Error("x"); };
    await settle(BOARD_POLL_MS);
    expect(q(".usage").textContent).toContain("Board not refreshed: /api/board: HTTP 404".replace("404", "404").slice(0, 21));
    expect(document.querySelectorAll(".card").length).toBeGreaterThan(0);
    boardBody = () => makeBoard();
    await settle(BOARD_POLL_MS);
    expect(q(".usage").textContent).not.toContain("Board not refreshed");
  });

  it("marks cards stale and shows the board-level error the server reports", async () => {
    await mountApp();
    boardBody = () => ({ ...makeBoard(), error: { code: "internal", message: "todo MCP unreachable" } });
    await settle(BOARD_POLL_MS);
    expect(q(".usage").textContent).toContain("Todo notes unavailable (internal): todo MCP unreachable.");
    expect(Object.hasOwn(q(".board-host").dataset, "stale")).toBe(true);
    expect(document.querySelectorAll(".card").length).toBeGreaterThan(0);
    boardBody = () => ({ ...makeBoard(), error: null });
    await settle(BOARD_POLL_MS);
    expect(Object.hasOwn(q(".board-host").dataset, "stale")).toBe(false);
  });

  it("reports usage failures without hiding the board", async () => {
    await mountApp();
    stubFetch({ "GET /api/board": () => makeBoard(), "GET /api/usage": new Response("x", { status: 500 }) });
    await settle(USAGE_POLL_MS);
    expect(q(".usage").textContent).toContain("Usage numbers unavailable: /api/usage: HTTP 500");
  });

  it("writes search, repo, sort and column into the hash and filters the cards", async () => {
    await mountApp();
    const search = q<HTMLInputElement>("input[name=q]");
    search.value = "gatelock";
    search.dispatchEvent(new Event("input"));
    expect(location.hash).toBe("#q=gatelock");
    expect(document.querySelectorAll(".card").length).toBeLessThan(5);
    q<HTMLSelectElement>("select[name=sort]").value = "cost";
    q("select[name=sort]").dispatchEvent(new Event("change"));
    q('.tab[data-col="running"]').click();
    expect(location.hash).toBe("#q=gatelock&sort=cost&col=running");
    q("button.btn").click();
    expect(location.hash).toBe("#sort=cost&col=running");
  });

  it("restores state from the hash on load and on hashchange", async () => {
    await mountApp("#col=running&repo=utils");
    expect(q<HTMLSelectElement>("select[name=repo]").value).toBe("utils");
    expect(q(".col[data-active]").getAttribute("data-col")).toBe("running");
    history.replaceState(null, "", "/#col=done");
    globalThis.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(q(".col[data-active]").getAttribute("data-col")).toBe("done");
  });

  it("opens the drawer from a card, pushes history and closes back to the board", async () => {
    await mountApp("#col=running");
    const push = vi.spyOn(history, "pushState");
    q(`.card[data-id="${READY}"]`).click();
    expect(push).toHaveBeenCalled();
    expect(location.hash).toBe(`#col=running&task=${READY}`);
    expect(q("ti-drawer").hidden).toBe(false);
    await settle(0);
    expect(q("#drawer-title").textContent).toBe("Widget shows next three tasks");
    q(".drawer-bar .btn:last-child").click();
    expect(location.hash).toBe("#col=running");
    expect(q("ti-drawer").hidden).toBe(true);
    q(`.card[data-id="${READY}"]`).click();
    expect(q("ti-drawer").hidden).toBe(false);
    history.replaceState(null, "", "/#col=running");
    globalThis.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(q("ti-drawer").hidden).toBe(true);
    globalThis.dispatchEvent(new HashChangeEvent("hashchange"));
    q(`.card[data-id="${READY}"]`).click();
    await settle(0);
    history.replaceState(null, "", "/#task=1fa1b2c3-0");
    globalThis.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(q("ti-drawer").dataset.task).toBe("1fa1b2c3-0");
  });

  it("keeps an open drawer when only the filters change", async () => {
    await mountApp(`#task=${READY}`);
    await settle(0);
    const calls = stub.calls.filter((c) => c.url.startsWith("/api/task/")).length;
    const search = q<HTMLInputElement>("input[name=q]");
    search.value = "w";
    search.dispatchEvent(new Event("input"));
    expect(q("ti-drawer").hidden).toBe(false);
    expect(stub.calls.filter((c) => c.url.startsWith("/api/task/"))).toHaveLength(calls);
  });

  it("opens the drawer for a task named in the first URL", async () => {
    await mountApp(`#task=${READY}`);
    await settle(0);
    expect(q("ti-drawer").hidden).toBe(false);
    expect(q("#drawer-title").textContent).toContain("Widget");
    await settle(BOARD_POLL_MS);
    expect(q("ti-drawer").hidden).toBe(false);
  });

  it("refreshes the board when the drawer reports a change", async () => {
    await mountApp(`#task=${READY}`);
    const before = stub.calls.filter((c) => c.url === "/api/board").length;
    q("ti-drawer").dispatchEvent(new CustomEvent("task-changed", { bubbles: true }));
    await settle(0);
    expect(stub.calls.filter((c) => c.url === "/api/board")).toHaveLength(before + 1);
  });

  it("does not repaint an unchanged board, keeps scroll and focus, and repaints each minute", async () => {
    const offsets = new WeakMap<Element, number>();
    Object.defineProperty(Element.prototype, "scrollTop", {
      configurable: true,
      get() { return offsets.get(this as Element) ?? 0; },
      set(value: number) { offsets.set(this as Element, value); },
    });
    await mountApp("#col=running");
    const card = q(`.card[data-id="${READY}"]`);
    card.focus();
    q(".col[data-active] .col-body").scrollTop = 40;
    await settle(BOARD_POLL_MS);
    expect(q(`.card[data-id="${READY}"]`)).toBe(card);
    await settle(61_000);
    const fresh = q(`.card[data-id="${READY}"]`);
    expect(fresh).not.toBe(card);
    expect(document.activeElement).toBe(fresh);
    expect(q(".col[data-active] .col-body").scrollTop).toBe(40);
  });

  it("offers the board's repos to a new task and opens the card the server answers", async () => {
    await mountApp("#repo=kuhyx%2Fwidget");
    const options = [...document.querySelectorAll("ti-new-task datalist option")].map((o) => o.getAttribute("value"));
    expect(options).toEqual(makeBoard().repos);
    q<HTMLButtonElement>("[data-new-task=open]").click();
    expect(q("ti-new-task [data-new-task=scope]").textContent).toBe("kuhyx/widget");
    const before = stub.calls.filter((c) => c.url === "/api/board").length;
    q("ti-new-task").dispatchEvent(new CustomEvent("task-created", { bubbles: true, detail: { id: READY } }));
    await settle(0);
    expect(location.hash).toContain(`task=${READY}`);
    expect(q("ti-drawer").hidden).toBe(false);
    expect(stub.calls.filter((c) => c.url === "/api/board")).toHaveLength(before + 1);
  });

  it("stops polling when removed", async () => {
    const app = await mountApp();
    app.remove();
    const calls = stub.calls.length;
    await settle(30_000);
    expect(stub.calls).toHaveLength(calls);
  });
});
