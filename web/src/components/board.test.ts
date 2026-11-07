import { afterEach, describe, expect, it, vi } from "vitest";

import { renderBoard } from "@/components/board-columns";
import { renderCard, statusChip } from "@/components/card";
import { createToolbar } from "@/components/toolbar";
import { renderUsage } from "@/components/usage-strip";
import { buildView } from "@/lib/board-model";
import { DEFAULT_STATE, type ViewState } from "@/lib/hash-state";
import { makeUsage } from "@/test/fixture-detail";
import { makeBoard, makeCards, NOW } from "@/test/fixtures";

const board = makeBoard();
const handlers = () => ({ onColumn: vi.fn(), onOpen: vi.fn() });
const mount = (node: Node) => {
  document.body.replaceChildren(node);
  return node as HTMLElement;
};

afterEach(() => {
  document.body.replaceChildren();
});

describe("renderCard", () => {
  it("[T1106] labels the needs category and shows the partial outcome", () => {
    const card = makeCards().find((c) => c.status === "needs_you");
    if (card === undefined) throw new Error("fixture");
    const partial = { deferred: ["C7"], done: ["C1", "C2", "C4"], followup_id: "abcd1234", open: ["C3", "C5"] };
    const text = renderCard({ ...card, partial }, NOW).textContent;
    expect(text).toContain("Questions");
    expect(text).toContain("partial: 3/5, follow-up abcd1234");
    expect(text).toContain("after ship: C7");
    const open = { ...partial, deferred: [], followup_id: null, open: ["C3"] };
    expect(renderCard({ ...card, partial: open }, NOW).textContent).toContain("partial: 3/4");
    expect(renderCard({ ...card, needs: { ...card.needs!, category: "auto" } }, NOW).textContent).toContain("Fixing itself");
  });

  it("[T1803] does not repeat the needs text when it equals the current line", () => {
    const card = makeCards().find((c) => c.status === "needs_you");
    if (card?.needs == null) throw new Error("fixture");
    const same = { ...card, current: "5 open question(s) from Claude", needs: { ...card.needs, text: "5 open question(s) from Claude" } };
    const element = renderCard(same, NOW);
    expect(element.querySelector(".card-needs")).toBeNull();
    expect(element.textContent.split("5 open question(s)")).toHaveLength(2);
  });

  it("[T1802] names the repo in the meta line only when asked", () => {
    const card = makeCards().find((c) => c.repo !== null);
    const mine = makeCards().find((c) => c.repo === null);
    if (mine === undefined || card?.repo == null) throw new Error("fixture");
    expect(renderCard(card, NOW, true).querySelector(".card-meta")?.textContent).toContain(card.repo);
    expect(renderCard(mine, NOW, true).querySelector(".card-meta")?.textContent).toContain("Yours");
    expect(renderCard(card, NOW).querySelector(".card-meta")?.textContent).not.toContain(card.repo);
  });

  it("shows server words only, no raw objects", () => {
    const card = makeCards().find((c) => c.status === "needs_you");
    if (card === undefined) throw new Error("fixture");
    const element = renderCard(card, NOW);
    expect(element.dataset.status).toBe("needs_you");
    expect(element.textContent).toContain("Answer 2 questions so Claude can plan.");
    expect(element.textContent).toContain(`#${card.id}`);
    expect(element.textContent).not.toMatch(/\[object Object\]|undefined|NaN/v);
  });

  it("names the resume time for a paused card and hides cost at zero", () => {
    const paused = makeCards().find((c) => c.status === "paused_limit");
    const idle = makeCards()[0];
    if (paused === undefined || idle === undefined) throw new Error("fixture");
    expect(renderCard(paused, NOW).textContent).toMatch(/resumes in 3 h 0 min \(\d\d:\d\d\)/v);
    expect(renderCard(idle, NOW).textContent).not.toContain("$");
    expect(statusChip("ready_to_ship").textContent).toBe("Ready to ship");
  });

  it("renders markup in a title as text", () => {
    const card = makeCards().find((c) => c.title.includes("<b>"));
    if (card === undefined) throw new Error("fixture");
    const element = renderCard(card, NOW);
    expect(element.querySelector("b")).toBeNull();
    expect(element.querySelector(".card-title")?.textContent).toContain("<b>height</b>");
  });
});

describe("renderBoard", () => {
  it("draws five columns with counts and groups by repo", () => {
    const root = mount(renderBoard(buildView(board, DEFAULT_STATE), DEFAULT_STATE, NOW, handlers()));
    expect([...root.querySelectorAll(".col")].map((c) => c.getAttribute("data-col"))).toEqual(["backlog", "running", "needs_you", "ready", "done"]);
    expect(root.querySelectorAll(".card")).toHaveLength(38);
    expect(root.querySelector('.col[data-col="backlog"] .group-name')).toBeNull();
    expect(root.querySelector('.col[data-col="needs_you"] .card-meta')?.textContent).toMatch(/ · /v);
    const grouped = { ...DEFAULT_STATE, sort: "priority" as const };
    const byRepo = mount(renderBoard(buildView(board, grouped), grouped, NOW, handlers()));
    expect(byRepo.querySelector('.col[data-col="backlog"] .group-name')?.textContent).toBe("Yours");
    expect(root.querySelector(".col[data-active]")?.getAttribute("data-col")).toBe("needs_you");
    expect(root.querySelector('.tab[aria-current="true"]')?.textContent).toContain("Needs you");
  });

  it("reports clicks on cards and tabs", () => {
    const h = handlers();
    const root = mount(renderBoard(buildView(board, DEFAULT_STATE), DEFAULT_STATE, NOW, h));
    root.querySelector<HTMLElement>(".card")?.click();
    root.querySelector<HTMLElement>('.tab[data-col="done"]')?.click();
    expect(h.onOpen).toHaveBeenCalledOnce();
    expect(h.onColumn).toHaveBeenCalledWith("done");
  });

  it("shows filtered counts and says why a column is empty", () => {
    const state: ViewState = { ...DEFAULT_STATE, q: "zzzz" };
    const root = mount(renderBoard(buildView(board, state), state, NOW, handlers()));
    expect(root.querySelector(".tab .count")?.textContent).toBe("0 of 21");
    expect(root.querySelector(".empty")?.textContent).toContain("No note here matches");
    const none = makeBoard([]);
    const empty = mount(renderBoard(buildView(none, DEFAULT_STATE), DEFAULT_STATE, NOW, handlers()));
    expect(empty.querySelector(".empty")?.textContent).toBe("Nothing in this column.");
    const unfilteredEmpty = makeBoard(makeCards().filter((c) => c.column === "backlog"));
    const some = mount(renderBoard(buildView(unfilteredEmpty, DEFAULT_STATE), DEFAULT_STATE, NOW, handlers()));
    expect(some.querySelector('.col[data-col="done"] .empty')?.textContent).toBe("Nothing in this column.");
  });
});

describe("toolbar", () => {
  it("reports search, repo and sort changes and clear", () => {
    const onChange = vi.fn();
    const toolbar = createToolbar({ onChange });
    mount(toolbar.el);
    toolbar.update(board, { ...DEFAULT_STATE, q: "abc", repo: "todo" });
    expect(toolbar.el.querySelector<HTMLInputElement>("input")?.value).toBe("abc");
    expect(toolbar.el.querySelector<HTMLButtonElement>("button")?.hidden).toBe(false);
    const search = toolbar.el.querySelector<HTMLInputElement>("input[name=q]");
    const repository = toolbar.el.querySelector<HTMLSelectElement>("select[name=repo]");
    const sort = toolbar.el.querySelector<HTMLSelectElement>("select[name=sort]");
    if (!search || !repository || !sort) throw new Error("fields");
    search.value = "x";
    search.dispatchEvent(new Event("input"));
    repository.value = "utils";
    repository.dispatchEvent(new Event("change"));
    sort.value = "cost";
    sort.dispatchEvent(new Event("change"));
    sort.value = "bogus";
    sort.dispatchEvent(new Event("change"));
    toolbar.el.querySelector<HTMLButtonElement>("button")?.click();
    expect(onChange.mock.calls.map((call: unknown[]) => call[0])).toEqual([{ q: "x" }, { repo: "utils" }, { sort: "cost" }, { sort: "priority" }, { q: "", repo: "" }]);
  });

  it("keeps the repo list stable, does not overwrite a focused search, and tolerates an unknown repo", () => {
    const toolbar = createToolbar({ onChange: vi.fn() });
    mount(toolbar.el);
    toolbar.update(board, DEFAULT_STATE);
    const options = toolbar.el.querySelector("select[name=repo]")?.children.length;
    expect(options).toBe(2 + board.repos.length);
    expect(toolbar.el.querySelector<HTMLButtonElement>("button")?.hidden).toBe(true);
    const search = toolbar.el.querySelector<HTMLInputElement>("input[name=q]");
    search?.focus();
    search?.setAttribute("value", "");
    if (search) search.value = "typing";
    toolbar.update(board, { ...DEFAULT_STATE, q: "stale" });
    expect(search?.value).toBe("typing");
    toolbar.update(board, { ...DEFAULT_STATE, repo: "gone" });
    expect(toolbar.el.querySelector<HTMLSelectElement>("select[name=repo]")?.value).toBe("gone");
    expect(toolbar.el.querySelector("select[name=repo]")?.children).toHaveLength(3 + board.repos.length);
  });
});

describe("renderUsage", () => {
  it("shows both windows, resets, running count, today's dollars and build", () => {
    const text = renderUsage(makeUsage(), board, null, "abc1234", NOW).textContent;
    expect(text).toContain("42%");
    expect(text).toContain("77%");
    expect(text).toMatch(/resets in 2 h 15 min/v);
    expect(text).toContain("Today $12.37");
    expect(renderUsage(makeUsage(), board, null, null, NOW).querySelector("a")?.getAttribute("href")).toBe("/usage");
    expect(text).toContain(`Running ${String(board.slots.used)}`);
    expect(text).not.toMatch(/Running \d+\s*\//v);
    expect(text).not.toContain("Slots");
    expect(renderUsage(makeUsage(), { ...board, slots: { used: 7 } }, null, null, NOW).textContent).toContain("Running 7");
    expect(text).toContain("abc1234");
  });

  it("colours by threshold and handles missing windows, errors, limit and credit use", () => {
    const usage = makeUsage();
    const hot = { ...usage, five_hour: { ...usage.five_hour!, utilization: 0.95 }, overage: { status: "allowed", using: true }, seven_day: null };
    const element = renderUsage(hot, { ...board, limit: { active: true, credits_available: true, until: NOW + 600 } }, "Board not refreshed: down", null, NOW);
    expect(element.querySelector('[data-tone="danger"]')).not.toBeNull();
    expect(element.textContent).toContain("no reading yet");
    expect(element.textContent).toContain("Using credits");
    expect(element.textContent).toContain("Plan limit reached: runs resume in 10 min");
    expect(element.textContent).toContain("Run on credits is available per task.");
    expect(element.querySelector('[role="alert"]')?.textContent).toBe("Board not refreshed: down");
    const warm = renderUsage({ ...usage, five_hour: { ...usage.five_hour!, utilization: 0.8 } }, null, null, null, NOW);
    expect(warm.querySelector('[data-tone="warn"]')).not.toBeNull();
    const noUntil = renderUsage(null, { ...board, limit: { active: true, credits_available: false, until: null } }, null, null, NOW);
    expect(noUntil.textContent).toContain("at an unknown time");
    expect(noUntil.textContent).toContain("Credits are not available.");
    expect(renderUsage(null, board, null, null, NOW).textContent).not.toContain("Today");
  });
});
