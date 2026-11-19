import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LINES, LOG, TASK } from "#fixtures/fixture-issues";
import { type FetchStub, stubFetch } from "#fixtures/net";
import { loadIssues } from "@/issues/api";
import { defineIssues, IssuesApp, POLL_MS } from "@/issues/app";
import { boot } from "@/issues/boot";
import { must } from "@/lib/dom";

const URL_ = `/api/task/${TASK}/issues`;
let body = LOG;
let status = 200;

async function flush(): Promise<void> {
  for (let index = 0; index < 6; index += 1) await vi.advanceTimersByTimeAsync(0);
}

function stub(): FetchStub {
  return stubFetch({ [`GET ${URL_}`]: () => new Response(body, { headers: { "Content-Type": "application/x-ndjson" }, status }) });
}

async function mount(hash = `#task=${TASK}`): Promise<{ app: IssuesApp; net: FetchStub }> {
  globalThis.location.hash = hash;
  const net = stub();
  const app = new IssuesApp();
  document.body.append(app);
  await flush();
  return { app, net };
}

const qa = <T extends HTMLElement = HTMLElement>(root: ParentNode, selector: string): T[] => [...root.querySelectorAll<T>(selector)];
const lines = (app: HTMLElement): string[] => qa(app, "tbody tr").map((row) => row.dataset.line ?? "");
const click = async (element: HTMLElement): Promise<void> => {
  element.click();
  await flush();
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-20T08:00:00.000Z"));
  defineIssues();
  body = LOG;
  status = 200;
});

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  globalThis.location.hash = "";
});

describe("the issue log page", () => {
  it("[T2094] shows the log as a readable table, newest first, with symptom and action in full", async () => {
    const { app } = await mount();
    expect(must<HTMLElement>(app, ".task-id").textContent).toBe(TASK);
    expect(must<HTMLAnchorElement>(app, "a.back").getAttribute("href")).toBe(`/#task=${TASK}`);
    expect(lines(app)).toEqual(["6", "5", "3", "2", "1", "4"]);
    const second = must<HTMLElement>(app, 'tr[data-line="2"]');
    expect(must<HTMLElement>(second, ".col-symptom .prose").textContent).toContain("8 more pins behind latest stable");
    expect(must<HTMLElement>(second, ".col-action .prose").textContent).toBe("Rerun worker with task-b.md listing every exact pin bump");
    expect(must<HTMLElement>(second, ".col-ts time").textContent).toBe("1h");
    expect(must<HTMLElement>(second, ".col-ts").title).not.toBe("");
    expect(must<HTMLElement>(app, 'tr[data-line="1"] .col-model .none').title).toBe("no model");
    expect(must<HTMLElement>(app, 'tr[data-line="4"] .raw-line').textContent).toBe(LINES[3]);
    expect(app.textContent).not.toMatch(/\[object Object\]|undefined|NaN/v);
  });

  it("is text-free outside the log's own words: every control carries its name in aria-label and title", async () => {
    const { app } = await mount();
    for (const control of qa(app, "button, a, .mark")) {
      expect(control.getAttribute("aria-label") ?? "").not.toBe("");
      expect(control.title).toBe(control.getAttribute("aria-label"));
    }
    expect(qa(app, ".states .chip").map((chip) => [chip.dataset.state, chip.textContent])).toEqual([["all", "6"], ["open", "3"], ["fixed", "2"], ["raw", "1"]]);
    expect(must<HTMLElement>(app, ".shown-count").textContent).toBe("6/6");
    expect(must<HTMLAnchorElement>(app, "a.raw-link").getAttribute("href")).toBe(URL_);
  });

  it("filters by state, phase, model, repo and search, keeps it in the hash, and resets", async () => {
    const { app } = await mount();
    await click(must<HTMLElement>(app, '.states [data-state="fixed"]'));
    expect(lines(app)).toEqual(["3", "1"]);
    expect(globalThis.location.hash).toBe(`#task=${TASK}&state=fixed`);
    await click(must<HTMLElement>(app, '.states [data-state="all"]'));
    await click(must<HTMLElement>(app, '[data-key="phase"] [data-value="prompt"]'));
    expect(lines(app)).toEqual(["5", "2"]);
    expect(must<HTMLElement>(app, '[data-key="phase"] [data-value="prompt"]').getAttribute("aria-pressed")).toBe("true");
    await click(must<HTMLElement>(app, '[data-key="phase"] [data-value="prompt"]'));
    await click(must<HTMLElement>(app, '[data-key="model"] [data-value="free-best"]'));
    expect(lines(app)).toEqual(["3", "2"]);
    await click(must<HTMLElement>(app, '[data-key="model"] [data-value="free-best"]'));
    const repo = must<HTMLSelectElement>(app, ".toolbar select");
    repo.value = "kuhyx/panel";
    repo.dispatchEvent(new Event("change"));
    await flush();
    expect(lines(app)).toEqual(["6", "5"]);
    const search = must<HTMLInputElement>(app, 'input[type="search"]');
    search.value = "ci.yml";
    search.dispatchEvent(new Event("input"));
    await flush();
    expect(lines(app)).toEqual(["5"]);
    expect(must<HTMLElement>(app, ".shown-count").textContent).toBe("1/6");
    const reset = must<HTMLButtonElement>(app, ".toolbar .icon-btn:not(.raw-link)");
    expect(reset.hidden).toBe(false);
    await click(reset);
    expect(lines(app)).toHaveLength(6);
    expect(globalThis.location.hash).toBe(`#task=${TASK}`);
    expect(reset.hidden).toBe(true);
  });

  it("keeps a repo picked in the hash in the picker even when the log has none of it", async () => {
    const { app } = await mount(`#task=${TASK}&repo=kuhyx/gone`);
    expect(qa<HTMLOptionElement>(app, ".toolbar option").map((option) => option.value)).toContain("kuhyx/gone");
    expect(lines(app)).toEqual([]);
  });

  it("sorts on every header: ascending, descending, then back to newest first", async () => {
    const { app } = await mount();
    const head = (key: string): HTMLButtonElement => must<HTMLButtonElement>(app, `th[data-key="${key}"] button`);
    for (const key of ["ts", "child", "phase", "model", "state", "symptom", "action"]) {
      await click(head(key));
      expect(must<HTMLElement>(app, `th[data-key="${key}"]`).getAttribute("aria-sort")).toBe("ascending");
    }
    await click(head("ts"));
    expect(lines(app)).toEqual(["1", "2", "3", "5", "6", "4"]);
    await click(head("ts"));
    expect(must<HTMLElement>(app, 'th[data-key="ts"]').getAttribute("aria-sort")).toBe("descending");
    await click(head("ts"));
    expect(lines(app)).toEqual(["6", "5", "3", "2", "1", "4"]);
    must<HTMLElement>(app, 'th[data-key="child"] button').dispatchEvent(new MouseEvent("click", { shiftKey: true }));
    await flush();
    expect(globalThis.location.hash).toContain("t.i.sort=child");
  });

  it("polls every 5 s, redraws only when the log changed, and keeps the scroll", async () => {
    const { app, net } = await mount();
    const table = must<HTMLElement>(app, "table");
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(net.calls.filter((call) => call.url === URL_)).toHaveLength(2);
    expect(must<HTMLElement>(app, "table")).toBe(table);
    body = `${LOG}${LINES[0] ?? ""}\n`;
    must<HTMLElement>(app, "main").scrollTop = 40;
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(lines(app)).toHaveLength(7);
    expect(must<HTMLElement>(app, "main").scrollTop).toBe(40);
  });

  it("shows a check for an empty log and an alert for an unknown task or a missing id", async () => {
    body = "";
    const empty = await mount();
    expect(must<HTMLElement>(empty.app, ".state-done").title).toBe("no issues logged");
    expect(must<HTMLElement>(empty.app, ".toolbar").hidden).toBe(true);
    document.body.replaceChildren();
    status = 404;
    const unknown = await mount();
    expect(must<HTMLElement>(unknown.app, ".state-failed").title).toBe("the server knows no such task");
    document.body.replaceChildren();
    const none = await mount("");
    expect(must<HTMLElement>(none.app, ".state-failed").title).toBe("no task id in the address");
    expect(must<HTMLAnchorElement>(none.app, "a.back").getAttribute("href")).toBe("/");
    expect(must<HTMLAnchorElement>(none.app, "a.raw-link").getAttribute("href")).toBe("#");
    expect(none.net.calls).toEqual([]);
  });

  it("names a failed load and retries on click, keeping the last good table", async () => {
    status = 500;
    const { app } = await mount();
    expect(must<HTMLElement>(app, ".failure").title).toBe(`${URL_}: HTTP 500`);
    expect(app.querySelector("table")).toBeNull();
    status = 200;
    await click(must<HTMLElement>(app, ".failure button"));
    expect(app.querySelector(".failure")).toBeNull();
    status = 500;
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(app.querySelector(".failure")).not.toBeNull();
    expect(lines(app)).toHaveLength(6);
  });

  it("reloads when the hash names another task and only redraws when it keeps the task", async () => {
    const { app, net } = await mount();
    globalThis.location.hash = `#task=${TASK}&state=open`;
    globalThis.dispatchEvent(new HashChangeEvent("hashchange"));
    await flush();
    expect(lines(app)).toEqual(["6", "5", "2"]);
    expect(net.calls).toHaveLength(1);
    net.routes.set("GET /api/task/bbbb2222-0/issues", () => new Response("", { status: 200 }));
    globalThis.location.hash = "#task=bbbb2222-0";
    globalThis.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(app.querySelector(".spinner")).not.toBeNull();
    await flush();
    expect(must<HTMLElement>(app, ".state-done")).toBeDefined();
    app.remove();
    await vi.advanceTimersByTimeAsync(POLL_MS * 2);
    expect(net.calls).toHaveLength(2);
  });
});

describe("loadIssues and boot", () => {
  it("rejects when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("down")));
    await expect(loadIssues(TASK)).rejects.toThrow("cannot reach the server");
  });

  it("registers the page element and starts the build watcher", async () => {
    vi.useRealTimers();
    const net = stubFetch({ "GET /version": { build: "abc1234", version: "0.1.0" } });
    const stop = boot();
    expect(customElements.get("issues-app")).toBe(IssuesApp);
    await vi.waitFor(() => { expect(net.calls.map((call) => call.url)).toContain("/version"); });
    stop();
  });
});
