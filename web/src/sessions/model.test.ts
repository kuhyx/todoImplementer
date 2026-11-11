import { describe, expect, it } from "vitest";

import { make, sessionRows, sid } from "#fixtures/fixture-sessions";
import {
  ageLabel, EMPTY_QUERY, groupRuns, projectsOf, readQuery, selectedIds, statusCounts, toItem, visibleItems, writeQuery,
} from "@/sessions/model";

const NOW = Date.parse("2026-11-20T08:00:00.000Z");
const ids = (query = EMPTY_QUERY): string[] => visibleItems(sessionRows(), query, NOW).map((item) => item.id);
const n = (...numbers: number[]): string[] => numbers.map((number_) => sid(number_));

describe("the hash", () => {
  it("is empty for the empty query and reads back to it", () => {
    expect(writeQuery(EMPTY_QUERY)).toBe("");
    expect(readQuery("")).toEqual(EMPTY_QUERY);
    expect(readQuery("#")).toEqual(EMPTY_QUERY);
  });

  it("round-trips every key", () => {
    const query = { ...EMPTY_QUERY, mark: "tag" as const, older: 3, project: "alpha", q: "app 2", showDone: true, sort: [{ desc: true, key: "age" }, { desc: false, key: "title" }], statuses: ["question" as const, "running" as const] };
    const hash = writeQuery(query);
    expect(hash).toContain("done=1");
    expect(readQuery(hash)).toEqual(query);
  });

  it("drops what it does not know: bad mark, bad status, bad sort key, zero or junk idle days", () => {
    const query = readQuery("#mark=nope&status=ghost,done&older=0&t.s.sort=-nothing,-group");
    expect(query).toEqual({ ...EMPTY_QUERY, sort: [{ desc: true, key: "group" }], statuses: ["done"] });
    expect(readQuery("#older=abc").older).toBeNull();
    expect(readQuery("#older=2.5").older).toBe(2.5);
  });
});

describe("visibleItems", () => {
  it("keeps the server's order and hides done sessions by default", () => {
    expect(ids()).toEqual(n(1, 2, 3, 4, 5));
  });

  it("shows done sessions with show-done, with a done mark filter, or when their own status is ticked", () => {
    expect(ids({ ...EMPTY_QUERY, showDone: true })).toEqual(n(1, 2, 3, 4, 5, 6, 7, 8));
    expect(ids({ ...EMPTY_QUERY, mark: "manual" })).toEqual(n(6));
    expect(ids({ ...EMPTY_QUERY, mark: "tag" })).toEqual(n(7, 8));
    expect(ids({ ...EMPTY_QUERY, statuses: ["done"] })).toEqual(n(7));
    expect(ids({ ...EMPTY_QUERY, statuses: ["continuing"] })).toEqual(n(8));
    // A ticked "question" chip does not reveal the question session that was marked done by hand.
    expect(ids({ ...EMPTY_QUERY, statuses: ["question"] })).toEqual(n(3));
  });

  it("filters by status, project and mark", () => {
    expect(ids({ ...EMPTY_QUERY, statuses: ["running", "untagged"] })).toEqual(n(4, 5));
    expect(ids({ ...EMPTY_QUERY, project: "alpha" })).toEqual(n(2));
    expect(ids({ ...EMPTY_QUERY, mark: "open" })).toEqual(n(1, 2, 3, 4, 5));
  });

  it("filters by idle days and never counts a session with no time as old", () => {
    expect(ids({ ...EMPTY_QUERY, older: 8 })).toEqual(n(1, 2));
    expect(ids({ ...EMPTY_QUERY, older: 0.5 })).toEqual(n(1, 2, 3, 5));
  });

  it("searches project, title, cwd, id and status words, fuzzily", () => {
    expect(ids({ ...EMPTY_QUERY, q: "alpha" })).toEqual(n(2));
    expect(ids({ ...EMPTY_QUERY, q: "zzz" })).toEqual([]);
    expect(ids({ ...EMPTY_QUERY, q: "app4 untagged" })).toEqual(n(4));
    expect(ids({ ...EMPTY_QUERY, q: "app4 running" })).toEqual([]);
    expect(ids({ ...EMPTY_QUERY, q: "src/app4" })).toEqual(n(4));
    expect(ids({ ...EMPTY_QUERY, q: sid(5) })).toEqual(n(5));
    expect(ids({ ...EMPTY_QUERY, q: "needs action" })).toEqual(n(1, 2));
    expect(ids({ ...EMPTY_QUERY, q: "ssn1" })).toEqual(n(1));
  });

  it.each([
    [[{ desc: false, key: "group" }], n(1, 2, 3, 4, 5)],
    [[{ desc: true, key: "group" }], n(5, 4, 3, 1, 2)],
    [[{ desc: false, key: "age" }], n(5, 3, 1, 2, 4)],
    [[{ desc: false, key: "project" }], n(2, 1, 3, 4, 5)],
    [[{ desc: true, key: "title" }], n(5, 4, 2, 1, 3)],
    [[{ desc: false, key: "markRank" }], n(1, 2, 3, 4, 5)],
  ])("sorts by %j", (sort, expected) => {
    expect(ids({ ...EMPTY_QUERY, sort })).toEqual(expected);
  });

  it("sorts the mark column manual, tag, open", () => {
    const query = { ...EMPTY_QUERY, showDone: true, sort: [{ desc: false, key: "markRank" }] };
    expect(ids(query)).toEqual(n(6, 7, 8, 1, 2, 3, 4, 5));
  });
});

describe("helpers", () => {
  it("toItem ranks the age so ascending is youngest first and a missing time has none", () => {
    expect(toItem(make(1)).age).toBeLessThan(toItem(make(2, { last_ts: "2026-11-09T08:00:00.000Z" })).age ?? 0);
    expect(toItem(make(1, { last_ts: null })).age).toBeNull();
    expect(toItem(make(1, { last_ts: "garbage" })).age).toBeNull();
  });

  it("counts every status, zero included", () => {
    expect(statusCounts(sessionRows())).toEqual({ continuing: 1, done: 1, needs_action: 2, question: 2, running: 1, untagged: 1 });
  });

  it("lists projects sorted, plus a project the data no longer has", () => {
    expect(projectsOf(sessionRows(), "")).toEqual(["alpha", "app1", "app3", "app4", "app5", "app6", "app7", "app8"]);
    expect(projectsOf([], "gone")).toEqual(["gone"]);
  });

  it("groups contiguous runs of the server's urgency groups", () => {
    const runs = groupRuns(visibleItems(sessionRows(), EMPTY_QUERY, NOW));
    expect(runs.map((run) => [run.group, run.items.length])).toEqual([[0, 2], [1, 1], [2, 1], [3, 1]]);
    expect(groupRuns([])).toEqual([]);
  });

  it("selectedIds keeps list order and drops ids that are no longer listed", () => {
    const items = visibleItems(sessionRows(), EMPTY_QUERY, NOW);
    expect(selectedIds(new Set([sid(1), sid(3), sid(99)]), items)).toEqual(n(1, 3));
  });

  it("ageLabel is minutes, hours or days, and empty without a time", () => {
    const at = (iso: string): string => ageLabel(toItem(make(1, { last_ts: iso })), NOW);
    expect(at("2026-11-20T07:55:00.000Z")).toBe("5m");
    expect(at("2026-11-20T03:00:00.000Z")).toBe("5h");
    expect(at("2026-11-10T08:00:00.000Z")).toBe("10d");
    expect(at("2026-11-20T09:00:00.000Z")).toBe("0m");
    expect(ageLabel(toItem(make(1, { last_ts: null })), NOW)).toBe("");
  });
});
