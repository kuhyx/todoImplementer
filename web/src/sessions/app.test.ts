import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { make, sid } from "#fixtures/fixture-sessions";
import { click, flush, ids, install, mount, POLL_MS, q, qa, uninstall } from "#fixtures/sessions-harness";
import { ARMED_MS } from "@/sessions/parts";

beforeEach(install);
afterEach(uninstall);

const row = (id: number): string => `tr[data-id="${sid(id)}"]`; // eslint-disable-line unicorn/no-unnecessary-parameters
const n = (...numbers: number[]): string[] => numbers.map((number_) => sid(number_));
const input = async (element: HTMLInputElement | HTMLSelectElement, value: string): Promise<void> => {
  element.value = value;
  element.dispatchEvent(new Event(element instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
  await flush();
};

describe("the list", () => {
  it("shows the open sessions in the server's order under one group row per urgency", async () => {
    const { app } = await mount();
    expect(ids(app)).toEqual(n(1, 2, 3, 4, 5));
    expect(qa(app, ".group-row").map((row) => row.dataset.group)).toEqual(["0", "1", "2", "3"]);
    expect(qa(app, ".group-count").map((count) => count.textContent)).toEqual(["2", "1", "1", "1"]);
    expect(qa(app, "tr[data-id]").map((row) => row.dataset.status)).toEqual(["needs_action", "needs_action", "question", "untagged", "running"]);
  });

  it("is text-free: pills and buttons carry icons and names in aria-label and title, numbers are the only text", async () => {
    const { app } = await mount();
    for (const pill of qa(app, ".pill, .mark")) {
      expect(pill.textContent).toBe("");
      expect(pill.getAttribute("aria-label")).toBe(pill.title);
      expect(pill.title).not.toBe("");
    }
    for (const button of qa(app, ".toolbar button, thead button, .row-actions button")) {
      expect(button.getAttribute("aria-label") ?? "").not.toBe("");
      expect(button.title).toBe(button.getAttribute("aria-label"));
    }
    const toolbar = q(app, ".toolbar").cloneNode(true) as HTMLElement;
    toolbar.querySelector("select")?.remove();
    expect(toolbar.textContent).toMatch(/^[\d\/]*$/v);
    expect(app.textContent).not.toMatch(/\[object Object\]|undefined|NaN/v);
  });

  it("shows a title, falls back to the id for an untitled session, and the idle time as a number", async () => {
    const { app } = await mount();
    const titles = qa(app, ".title-btn").map((button) => button.textContent);
    expect(titles).toEqual(["Session 1", "Session 2", "33333333", "Session 4", "Session 5"]);
    expect(qa(app, "td.num").map((cell) => cell.textContent)).toEqual(qa(app, "td.num").map((cell) => cell.textContent.trim()));
    expect(qa(app, "td.num")[3]?.textContent).toBe("");
  });

  it("expands a row to cwd, id, last prompt and the markdown reply, and collapses it again", async () => {
    const { app } = await mount();
    await click(q(app, `tr[data-id="${sid(1)}"] .title-btn`));
    const detail = q(app, ".detail-row");
    expect(detail.textContent).toContain("/home/kuhy/src/app1");
    expect(detail.textContent).toContain(sid(1));
    expect(detail.textContent).toContain("prompt 1");
    expect(q(detail, "code, .md-h, p").textContent).not.toBe("");
    await click(q(app, `tr[data-id="${sid(1)}"]`));
    expect(app.querySelector(".detail-row")).toBeNull();
  });

  it("does not expand a row when its checkbox or an action is clicked", async () => {
    const { app } = await mount();
    await click(q(app, `tr[data-id="${sid(1)}"] input[type="checkbox"]`));
    await click(q(app, `tr[data-id="${sid(1)}"] .row-actions button`));
    expect(app.querySelector(".detail-row")).toBeNull();
  });
});

describe("filters, search and the hash", () => {
  it("has a sortable header per column that reorders, drops the group rows and writes the hash", async () => {
    const { app } = await mount();
    const descending: boolean[] = [];
    for (const key of ["group", "age", "project", "title", "markRank"]) {
      const before = ids(app);
      await click(q(app, `th[data-key="${key}"] button`));
      expect(q(app, `th[data-key="${key}"]`).getAttribute("aria-sort")).toBe("ascending");
      expect(globalThis.location.hash).toContain(`t.s.sort=${key}`);
      expect(app.querySelector(".group-row")).toBeNull();
      await click(q(app, `th[data-key="${key}"] button`));
      expect(q(app, `th[data-key="${key}"]`).getAttribute("aria-sort")).toBe("descending");
      descending.push(ids(app).join(',') !== before.join(','));
      await click(q(app, `th[data-key="${key}"] button`));
      expect(q(app, `th[data-key="${key}"]`).getAttribute("aria-sort")).toBe("none");
      expect(ids(app)).toEqual(before);
    }
    expect(descending).toEqual([true, true, true, true, false]);
    expect(globalThis.location.hash).toBe("");
  });

  it("extends the sort with shift", async () => {
    const { app } = await mount();
    await click(q(app, 'th[data-key="project"] button'));
    await click(q(app, 'th[data-key="title"] button'), { shiftKey: true });
    expect(globalThis.location.hash).toContain("t.s.sort=project%2Ctitle");
  });

  it("searches fuzzily as you type and keeps what you typed", async () => {
    const { app } = await mount();
    const box = q<HTMLInputElement>(app, 'input[type="search"]');
    await input(box, "alpha");
    expect(ids(app)).toEqual(n(2));
    expect(globalThis.location.hash).toBe("#t.s.q=alpha");
    expect(box.value).toBe("alpha");
  });

  it("filters by status chip, with counts, and by project", async () => {
    const { app } = await mount();
    expect(qa(app, ".chip-count").map((count) => count.textContent)).toEqual(["2", "2", "1", "1", "1", "1"]);
    await click(q(app, '.chip[data-status="running"]'));
    expect(ids(app)).toEqual(n(5));
    expect(q(app, '.chip[data-status="running"]').getAttribute("aria-pressed")).toBe("true");
    await click(q(app, '.chip[data-status="running"]'));
    expect(ids(app)).toEqual(n(1, 2, 3, 4, 5));
    await input(q<HTMLSelectElement>(app, "select"), "alpha");
    expect(ids(app)).toEqual(n(2));
  });

  it("filters by idle days, by mark and by show-done, and resets them all", async () => {
    const { app } = await mount();
    await input(q<HTMLInputElement>(app, "input.idle"), "8");
    expect(ids(app)).toEqual(n(1, 2));
    await input(q<HTMLInputElement>(app, "input.idle"), "");
    await click(q(app, '.marks [data-mark="manual"]'));
    expect(ids(app)).toEqual(n(6));
    await click(q(app, '.marks [data-mark="all"]'));
    await click(q(app, '.toolbar button[aria-label="show done sessions"]'));
    expect(ids(app)).toHaveLength(8);
    expect(q(app, ".shown-count").textContent).toBe("8/8");
    expect(q<HTMLButtonElement>(app, 'button[aria-label="reset the filters"]').hidden).toBe(false);
    await click(q(app, 'button[aria-label="reset the filters"]'));
    expect(ids(app)).toHaveLength(5);
    expect(globalThis.location.hash).toBe("");
  });

  it("opens from a hash and follows hash changes", async () => {
    const { app } = await mount("#status=question&project=app3");
    expect(ids(app)).toEqual(n(3));
    expect(q<HTMLSelectElement>(app, "select").value).toBe("app3");
    globalThis.location.hash = "#t.s.q=alpha";
    globalThis.dispatchEvent(new HashChangeEvent("hashchange"));
    await flush();
    expect(ids(app)).toEqual(n(2));
    expect(q<HTMLInputElement>(app, 'input[type="search"]').value).toBe("alpha");
  });
});

describe("live refresh", () => {
  it("polls, keeps the table when nothing changed, and redraws when it did", async () => {
    const harness = await mount();
    const table = q(harness.app, "table");
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(harness.stub.calls.filter((call) => call.url === "/api/sessions")).toHaveLength(2);
    expect(q(harness.app, "table")).toBe(table);
    harness.rows = [make(9), ...harness.rows];
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(ids(harness.app)[0]).toBe(sid(9));
  });

  it("[T1926] a poll with changed data does not reset an armed delete or take the focus; it applies once focus leaves", async () => {
    const harness = await mount();
    await vi.advanceTimersByTimeAsync(POLL_MS - ARMED_MS / 2);
    const trash = q<HTMLButtonElement>(harness.app, `${row(1)} button[aria-label^="move to the trash"]`);
    await click(trash);
    trash.focus();
    harness.rows = [make(9), ...harness.rows];
    await vi.advanceTimersByTimeAsync(ARMED_MS / 2);
    expect(trash.dataset.armed).toBe("true");
    expect(document.activeElement).toBe(trash);
    expect(ids(harness.app)[0]).toBe(sid(1));
    await vi.advanceTimersByTimeAsync(ARMED_MS);
    expect(trash.dataset.armed).toBeUndefined();
    expect(ids(harness.app)[0]).toBe(sid(1));
    trash.blur();
    await flush();
    expect(ids(harness.app)[0]).toBe(sid(9));
  });

  it("[T1926] a poll with changed data waits while focus is inside the table and applies when it leaves", async () => {
    const harness = await mount();
    const box = q<HTMLInputElement>(harness.app, `${row(1)} input[type="checkbox"]`);
    box.focus();
    harness.rows = [make(9), ...harness.rows];
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(document.activeElement).toBe(box);
    expect(ids(harness.app)[0]).toBe(sid(1));
    box.blur();
    await flush();
    expect(ids(harness.app)[0]).toBe(sid(9));
  });

  it("drops a selected row that is gone after a refresh", async () => {
    const harness = await mount();
    await click(q(harness.app, `tr[data-id="${sid(1)}"] input`));
    harness.rows = harness.rows.slice(1);
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(harness.app.querySelector(".bulk-bar")).toBeNull();
  });

  it("shows a loader naming what it waits on while the first scan runs", async () => {
    const { app } = await mount("", { list: () => new Promise(() => {}) });
    const spinner = q(app, '[role="progressbar"]');
    expect(spinner.textContent).toBe("");
    expect(spinner.title).toBe("reading the session transcripts");
    expect(spinner.getAttribute("aria-label")).toBe(spinner.title);
  });

  it("shows a failure first with a retry that loads the list", async () => {
    let isReady = false;
    const list = (): unknown => (isReady ? { scan_ms: 1, scanned: 0, sessions: [] } : Response.json({}, { status: 500 }));
    const { app } = await mount("", { list });
    expect(q(app, '[role="alert"]').title).toContain("HTTP 500");
    isReady = true;
    await click(q(app, '[role="alert"] button'));
    expect(app.querySelector('[role="alert"]')).toBeNull();
    expect(ids(app)).toEqual([]);
  });

  it("keeps the last list when a later refresh fails, and marks it", async () => {
    const harness = await mount();
    harness.stub.routes.set("GET /api/sessions", () => Response.json({}, { status: 500 }));
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(ids(harness.app)).toEqual(n(1, 2, 3, 4, 5));
    expect(q(harness.app, '[role="alert"]').getAttribute("aria-label")).toContain("500");
  });

  it("stops polling when it leaves the page", async () => {
    const harness = await mount();
    harness.app.remove();
    const before = harness.stub.calls.length;
    await vi.advanceTimersByTimeAsync(POLL_MS * 3);
    expect(harness.stub.calls).toHaveLength(before);
  });
});
