import { describe, expect, it } from "vitest";

import { LOG, NOW_S } from "#fixtures/fixture-issues";
import {
  ageLabel, EMPTY_QUERY, isoStamp, newestFirst, readQuery, stampLabel, stateCounts, tally, visibleIssues, writeQuery,
} from "@/issues/model";
import { parseLog } from "@/issues/schemas";

const issues = parseLog(LOG);
const lines = (query: Partial<typeof EMPTY_QUERY>): number[] => visibleIssues(issues, { ...EMPTY_QUERY, ...query }).map((issue) => issue.line);

describe("parseLog", () => {
  it("keeps every non-blank line in file order, numbering them from 1", () => {
    expect(issues.map((issue) => [issue.line, issue.state])).toEqual([[1, "fixed"], [2, "open"], [3, "fixed"], [4, "raw"], [5, "open"], [6, "open"]]);
    expect(issues[0]).toMatchObject({ child: "kuhyx/CV", model: "", phase: "start", ts: NOW_S - 7200 });
    expect(issues[1]?.model).toBe("free-best");
  });

  it("defaults the optional fields and keeps a line that is not an issue as a raw row", () => {
    expect(issues[5]).toMatchObject({ action: "", model: "", state: "open" });
    expect(issues[3]).toMatchObject({ child: "", state: "raw", symptom: "manager note: gateway flapped twice, see worker-3.log", ts: null });
    expect(parseLog('[1]\n{"ts":"x"}\n').map((issue) => issue.state)).toEqual(["raw", "raw"]);
    expect(parseLog("")).toEqual([]);
  });
});

describe("the hash", () => {
  it("round-trips task, filters, search and sort, and omits defaults", () => {
    const query = { ...EMPTY_QUERY, model: "free-best", phase: "prompt", q: "pin", repo: "kuhyx/CV", sort: [{ desc: true, key: "child" }], state: "open" as const, task: "aaaa1111-0" };
    const hash = writeQuery(query);
    expect(hash.startsWith("#task=aaaa1111-0&state=open")).toBe(true);
    expect(readQuery(hash)).toEqual(query);
    expect(writeQuery(EMPTY_QUERY)).toBe("");
    expect(readQuery("")).toEqual(EMPTY_QUERY);
  });

  it("drops an unknown state and a sort on an unknown column", () => {
    expect(readQuery("#task=x&state=bogus&t.i.sort=nope,-ts")).toMatchObject({ sort: [{ desc: true, key: "ts" }], state: "all" });
  });
});

describe("rows", () => {
  it("lists newest first, raw rows by their place in the file", () => {
    expect(lines({})).toEqual([6, 5, 3, 2, 1, 4]);
    expect(newestFirst(parseLog("a\nb\n")).map((issue) => issue.line)).toEqual([2, 1]);
  });

  it("filters by state, phase, model and repo, and searches every column", () => {
    expect(lines({ state: "fixed" })).toEqual([3, 1]);
    expect(lines({ state: "raw" })).toEqual([4]);
    expect(lines({ phase: "prompt" })).toEqual([5, 2]);
    expect(lines({ model: "free-best" })).toEqual([3, 2]);
    expect(lines({ repo: "kuhyx/panel" })).toEqual([6, 5]);
    expect(lines({ q: "gateway flapped" })).toEqual([4]);
    expect(lines({ q: "434" })).toEqual([3]);
  });

  it("sorts by a header over the newest-first order", () => {
    expect(lines({ sort: [{ desc: false, key: "child" }] })).toEqual([4, 1, 3, 2, 6, 5]);
    expect(lines({ sort: [{ desc: false, key: "ts" }] })).toEqual([1, 2, 3, 5, 6, 4]);
  });
});

describe("counts and labels", () => {
  it("tallies values most frequent first and counts each state", () => {
    expect(tally(issues, "phase")).toEqual([["output", 2], ["prompt", 2], ["start", 1]]);
    expect(tally(issues, "model")).toEqual([["free-best", 2], ["free-fast", 1]]);
    expect(stateCounts(issues)).toEqual({ all: 6, fixed: 2, open: 3, raw: 1 });
  });

  it("shows the age in s, m, h and d, and nothing for a raw row", () => {
    const now = NOW_S * 1000;
    expect([30, 600, 7200, 200_000].map((ago) => ageLabel(NOW_S - ago, now))).toEqual(["30s", "10m", "2h", "2d"]);
    expect(ageLabel(NOW_S + 5, now)).toBe("0s");
    expect(ageLabel(null, now)).toBe("");
  });

  it("gives the absolute time for the title and the datetime attribute", () => {
    const date = new Date(NOW_S * 1000);
    expect(stampLabel(NOW_S)).toBe(date.toLocaleString());
    expect(stampLabel(null)).toBe("");
    expect(isoStamp(NOW_S)).toBe("2026-11-20T08:00:00.000Z");
    expect(isoStamp(null)).toBeNull();
  });
});
