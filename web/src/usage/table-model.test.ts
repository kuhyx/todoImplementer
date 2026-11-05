import { describe, expect, it } from "vitest";

import { applyTable, type Column, cycleSort, distinct, EMPTY_TABLE, readTable, shown, writeTable } from "@/usage/table-model";

const columns: Column[] = [
  { key: "name", kind: "text", label: "Name" },
  { key: "cost", kind: "number", label: "Cost", show: (value) => `$${String(value)}` },
  { key: "tag", kind: "enum", label: "Tag" },
];
const rows = [
  { cost: 3, name: "alpha build", tag: "DONE" },
  { cost: null, name: "beta", tag: "RUNNING" },
  { cost: 10, name: "gamma ray", tag: "DONE" },
  { cost: 3, name: "delta", tag: null },
];
const names = (state = EMPTY_TABLE): unknown[] => applyTable(rows, columns, state).map((row) => row.name);

describe("hash grammar", () => {
  it("round-trips every field and keeps other tables", () => {
    const state = { filters: { cost: "1..5", tag: "=DONE" }, limit: 0, q: "al", sort: [{ desc: true, key: "cost" }, { desc: false, key: "name" }] };
    const parameters = writeTable(new URLSearchParams("t.other.q=x&cwd=a"), "t", state);
    expect(parameters.get("t.other.q")).toBe("x");
    expect(parameters.get("cwd")).toBe("a");
    expect(parameters.get("t.t.sort")).toBe("-cost,name");
    expect(readTable(parameters, "t")).toEqual(state);
  });

  it("reads defaults from an empty hash and drops bad limits", () => {
    expect(readTable(new URLSearchParams(), "t")).toEqual(EMPTY_TABLE);
    expect(readTable(new URLSearchParams("t.t.limit=abc&t.t.sort=-&t.t.f.name="), "t")).toEqual(EMPTY_TABLE);
  });

  it("writes nothing for an empty state", () => {
    expect(writeTable(new URLSearchParams("t.t.q=old"), "t", EMPTY_TABLE).toString()).toBe("");
  });
});

describe("applyTable", () => {
  it("returns all rows untouched with an empty state", () => {
    expect(names()).toEqual(["alpha build", "beta", "gamma ray", "delta"]);
  });

  it("fuzzy-searches every word across the displayed cells", () => {
    expect(names({ ...EMPTY_TABLE, q: "gmr" })).toEqual(["gamma ray"]);
    expect(names({ ...EMPTY_TABLE, q: "al bld" })).toEqual(["alpha build"]);
    expect(names({ ...EMPTY_TABLE, q: "$10" })).toEqual(["gamma ray"]);
    expect(names({ ...EMPTY_TABLE, q: "zzz" })).toEqual([]);
  });

  it("filters by range, enum and text", () => {
    expect(names({ ...EMPTY_TABLE, filters: { cost: "3..5" } })).toEqual(["alpha build", "delta"]);
    expect(names({ ...EMPTY_TABLE, filters: { cost: "..5" } })).toEqual(["alpha build", "delta"]);
    expect(names({ ...EMPTY_TABLE, filters: { cost: "5.." } })).toEqual(["gamma ray"]);
    expect(names({ ...EMPTY_TABLE, filters: { tag: "=DONE|RUNNING" } })).toHaveLength(3);
    expect(names({ ...EMPTY_TABLE, filters: { tag: "=—" } })).toEqual(["delta"]);
    expect(names({ ...EMPTY_TABLE, filters: { name: "~ray" } })).toEqual(["gamma ray"]);
    expect(names({ ...EMPTY_TABLE, filters: { name: "ph" } })).toEqual(["alpha build"]);
  });

  it("sorts numbers numerically, nulls last either way, ties by the next key", () => {
    const asc = [{ desc: false, key: "cost" }, { desc: false, key: "name" }];
    expect(names({ ...EMPTY_TABLE, sort: asc })).toEqual(["alpha build", "delta", "gamma ray", "beta"]);
    expect(names({ ...EMPTY_TABLE, sort: [{ desc: true, key: "cost" }] })).toEqual(["gamma ray", "alpha build", "delta", "beta"]);
    expect(names({ ...EMPTY_TABLE, sort: [{ desc: true, key: "tag" }, { desc: false, key: "cost" }] })[0]).toBe("beta");
    expect(names({ ...EMPTY_TABLE, sort: [{ desc: false, key: "cost" }, { desc: false, key: "tag" }] })).toHaveLength(4);
  });

  it("sorts text naturally and treats two nulls as equal", () => {
    const withGap = [{ k: null }, { k: "b10" }, { k: "b2" }, { k: null }];
    const out = applyTable(withGap, [], { ...EMPTY_TABLE, sort: [{ desc: false, key: "k" }] });
    expect(out.map((row) => row.k)).toEqual(["b2", "b10", null, null]);
  });
});

describe("helpers", () => {
  it("cycles none -> asc -> desc -> none, shift keeps others", () => {
    const first = cycleSort([], "a", false);
    expect(first).toEqual([{ desc: false, key: "a" }]);
    const second = cycleSort(first, "a", false);
    expect(second).toEqual([{ desc: true, key: "a" }]);
    expect(cycleSort(second, "a", false)).toEqual([]);
    expect(cycleSort(first, "b", true)).toEqual([{ desc: false, key: "a" }, { desc: false, key: "b" }]);
    expect(cycleSort(first, "b", false)).toEqual([{ desc: false, key: "b" }]);
    expect(cycleSort(cycleSort(first, "b", true), "a", true)).toEqual([{ desc: false, key: "b" }, { desc: true, key: "a" }]);
  });

  it("lists distinct values sorted and shows through the column formatter", () => {
    expect(distinct(rows, "tag")).toEqual(["—", "DONE", "RUNNING"]);
    expect(shown(columns[1]!, rows[0] as never)).toBe("$3");
    expect(shown(columns[0]!, rows[0] as never)).toBe("alpha build");
  });
});
