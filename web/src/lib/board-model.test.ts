import { describe, expect, it } from "vitest";

import { buildView, repoOptions, searchText, sortCards } from "@/lib/board-model";
import { DEFAULT_STATE, YOURS } from "@/lib/hash-state";
import { makeBoard, makeCards } from "@/test/fixtures";

const board = makeBoard();
const backlog = (view: ReturnType<typeof buildView>) => view.find((c) => c.id === "backlog");

describe("buildView", () => {
  it("puts every card in the server's column and keeps counts", () => {
    const view = buildView(board, DEFAULT_STATE);
    expect(view.map((c) => c.id)).toEqual(["backlog", "running", "needs_you", "ready", "done"]);
    expect(view.map((c) => c.shown)).toEqual(board.columns.map((c) => c.count));
    expect(view.flatMap((c) => c.groups.flatMap((g) => g.cards))).toHaveLength(38);
  });

  it("groups by repo with Yours first and repos A-Z", () => {
    const labels = backlog(buildView(board, DEFAULT_STATE))?.groups.map((g) => g.label) ?? [];
    expect(labels[0]).toBe("Yours");
    expect(labels.slice(1)).toEqual(labels.slice(1).toSorted((a, b) => a.localeCompare(b)));
  });

  it("filters by repo and by Yours", () => {
    const todo = buildView(board, { ...DEFAULT_STATE, repo: "todo" });
    expect(todo.flatMap((c) => c.groups.flatMap((g) => g.cards)).every((card) => card.repo === "todo")).toBe(true);
    const yours = buildView(board, { ...DEFAULT_STATE, repo: YOURS });
    expect(yours.flatMap((c) => c.groups.flatMap((g) => g.cards))).toHaveLength(7);
  });

  it("fuzzy-searches title, repo and id with every word required", () => {
    const find = (q: string) => buildView(board, { ...DEFAULT_STATE, q }).flatMap((c) => c.groups.flatMap((g) => g.cards));
    expect(find("dentist").map((c) => c.title)).toContain("Call the dentist about the crown");
    expect(find("dentist").length).toBeLessThan(38);
    expect(find("utils fuzzy")).toHaveLength(1);
    expect(find("gatelock").map((c) => c.repo)).toContain("gatelock");
    expect(find("zzzz")).toHaveLength(0);
    expect(find("17a1b2c3-0")).toHaveLength(1);
  });

  it("keeps the unfiltered total next to the shown count", () => {
    const view = buildView(board, { ...DEFAULT_STATE, q: "zzzz" });
    expect(view.every((c) => c.shown === 0 && c.total >= 0)).toBe(true);
    expect(backlog(view)?.total).toBe(board.columns[0]?.count);
  });
});

describe("sortCards", () => {
  const cards = makeCards();
  it("sorts by priority then recency", () => {
    const sorted = sortCards(cards.filter((c) => c.column === "backlog" && c.repo !== null), "priority");
    expect(sorted[0]?.priority).toBe("urgent");
  });
  it("sorts by updated, putting null last", () => {
    const sorted = sortCards(cards.filter((c) => c.column === "backlog"), "updated");
    expect(sorted.at(-1)?.updated).toBeNull();
  });
  it("sorts by title and by cost", () => {
    const titles = sortCards(cards, "title").map((c) => c.title);
    expect(titles).toEqual(titles.toSorted((a, b) => a.localeCompare(b)));
    expect(sortCards(cards, "cost")[0]?.cost_usd).toBe(5);
  });
  it("[T1105] sorts Needs you by server effort, easiest first", () => {
    const base = cards.find((c) => c.needs !== null);
    if (base?.needs == null) throw new Error("fixture");
    const hard = { ...base, id: "hhhhhhhh-0", needs: { ...base.needs, effort: 4 }, priority: "urgent" };
    const easy = { ...base, id: "eeeeeeee-0", needs: { ...base.needs, effort: 1 }, priority: "low" };
    expect(sortCards([hard, easy], "effort").map((c) => c.id)).toEqual(["eeeeeeee-0", "hhhhhhhh-0"]);
  });
  it("ranks unknown priorities last and breaks ties by id", () => {
    const [a, b] = cards;
    if (a === undefined || b === undefined) throw new Error("fixture");
    const odd = { ...a, priority: "someday" };
    expect(sortCards([{ ...b, priority: "low" }, odd], "priority")[0]?.priority).toBe("low");
    expect(sortCards([odd, { ...b, priority: "low" }], "priority")[0]?.priority).toBe("low");
    expect(sortCards([{ ...b, id: "bbbbbbbb" }, { ...b, id: "aaaaaaaa" }], "title").map((c) => c.id)).toEqual(["aaaaaaaa", "bbbbbbbb"]);
  });
});

describe("repoOptions", () => {
  it("lists all, yours and each repo with counts", () => {
    const options = repoOptions(board);
    expect(options.slice(0, 2).map((o) => [o.value, o.count])).toEqual([["", 38], [YOURS, 7]]);
    expect(options).toHaveLength(2 + board.repos.length);
    expect(options.find((o) => o.value === "todo")?.count).toBe(2);
  });
  it("omits Yours when every note has a repo", () => {
    const cards = makeCards().filter((c) => c.repo !== null);
    expect(repoOptions(makeBoard(cards)).some((o) => o.value === YOURS)).toBe(false);
  });
});

describe("searchText", () => {
  it("names Yours for repo-less notes and includes the needs text", () => {
    const yours = makeCards().find((c) => c.repo === null);
    const needy = makeCards().find((c) => c.needs !== null);
    expect(searchText(yours ?? makeCards()[0]!)).toContain("yours");
    expect(searchText(needy ?? makeCards()[0]!)).toContain("Answer 2 questions");
  });
});
