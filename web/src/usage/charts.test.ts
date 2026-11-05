import { describe, expect, it } from "vitest";

import { barChart, rankChart } from "@/usage/chart-bars";
import { emptyPlot, frame } from "@/usage/chart-frame";
import { intervalChart } from "@/usage/chart-intervals";
import { lineChart } from "@/usage/chart-line";
import { color, labelIndexes, linePath, niceAxis, scaleY, slotX } from "@/usage/chart-scale";
import { col, inferColumns } from "@/usage/columns";
import { cellText, compact, duration, share, stamp, usd } from "@/usage/format";

const fmt = (value: number): string => `<${String(value)}>`;
const hit = (figure: Element, index: number): SVGElement => figure.querySelectorAll<SVGElement>(".hit")[index]!;

describe("scale", () => {
  it("picks nice axes for any magnitude, including nothing", () => {
    expect(niceAxis(173).max).toBe(200);
    expect(niceAxis(0.43).max).toBeCloseTo(0.6);
    expect(niceAxis(0)).toEqual({ max: 1, ticks: [0, 0.5, 1] });
    expect(niceAxis(99_000).max).toBe(100_000);
    expect(niceAxis(30).max).toBe(30);
  });

  it("maps values into the plot and cycles colours", () => {
    expect(scaleY(0, 10)).toBeGreaterThan(scaleY(10, 10));
    expect(slotX(0, 2)).toBeLessThan(slotX(1, 2));
    expect(color(0)).toBe(color(5));
    expect(color(1)).not.toBe(color(0));
  });

  it("breaks the line at a null and spreads at most six labels", () => {
    expect(linePath([1, null, 2, 3], 4).match(/M/gv)).toHaveLength(2);
    expect(linePath([1, 2], 4).match(/M/gv)).toHaveLength(1);
    expect(labelIndexes(30)).toHaveLength(6);
    expect(labelIndexes(3)).toEqual([0, 1, 2]);
  });
});

describe("hover layer", () => {
  it("shows the crosshair and a tooltip with every series value, hides on leave, and works from the keyboard", () => {
    const figure = lineChart({ fmt, labels: ["a", "b", "c"], series: [{ color: "red", name: "S1", values: [1, null, 3] }, { color: "blue", name: "S2", values: [2, 2, 2] }], title: "T" });
    const tip = figure.querySelector<HTMLElement>(".tip")!;
    const cross = figure.querySelector(".cross")!;
    expect(tip.hidden).toBe(true);
    hit(figure, 1).dispatchEvent(new Event("mouseenter"));
    expect(tip.hidden).toBe(false);
    expect(tip.textContent).toContain("S1: —");
    expect(tip.textContent).toContain("S2: <2>");
    expect(cross.getAttribute("visibility")).toBe("visible");
    hit(figure, 1).dispatchEvent(new Event("mouseleave"));
    expect(tip.hidden).toBe(true);
    hit(figure, 0).dispatchEvent(new Event("focus"));
    expect(tip.textContent).toContain("S1: <1>");
    hit(figure, 0).dispatchEvent(new Event("blur"));
    expect(cross.getAttribute("visibility")).toBe("hidden");
  });

  it("has a legend for two series, none for one, and a table view of the same numbers", () => {
    const two = lineChart({ fmt, labels: ["a", "b"], series: [{ color: "red", name: "S1", values: [1, 2] }, { color: "blue", name: "S2", values: [null, 4] }], title: "T" });
    const one = lineChart({ fmt, labels: ["a"], series: [{ color: "red", name: "S1", values: [1] }], title: "T" });
    expect(two.querySelectorAll(".legend li")).toHaveLength(2);
    expect(one.querySelector(".legend")).toBeNull();
    expect(two.querySelector(".chart-table")?.textContent).toContain("<4>");
    expect(two.querySelector(".chart-table")?.textContent).toContain("—");
  });

  it("draws no markers when there are many points and copes with no data", () => {
    const labels = Array.from({ length: 30 }, (_, index) => String(index));
    const many = lineChart({ fmt, labels, series: [{ color: "red", name: "S", values: labels.map(() => 1) }], title: "T" });
    expect(many.querySelectorAll(".marker")).toHaveLength(0);
    expect(lineChart({ fmt, labels: [], series: [], title: "T" }).querySelector("svg")).not.toBeNull();
    expect(frame("T", emptyPlot(), [], [], fmt).figure.querySelector(".hit")).toBeNull();
  });
});

describe("bars", () => {
  it("stacks values with a surface gap and skips zero segments", () => {
    const figure = barChart({ fmt, labels: ["a", "b"], series: [{ color: "red", name: "S1", values: [1, 0] }, { color: "blue", name: "S2", values: [null, 2] }], title: "T" });
    expect(figure.querySelectorAll("rect.bar")).toHaveLength(2);
    expect(figure.querySelector("rect.bar")?.getAttribute("stroke")).toBe("var(--surface-1)");
    expect(barChart({ fmt, labels: [], series: [], title: "T" }).querySelectorAll("rect.bar")).toHaveLength(0);
  });

  it("ranks rows with direct value labels and truncates long names", () => {
    const figure = rankChart("R", [{ label: "x".repeat(40), value: 5 }, { label: "b", value: 0 }], fmt);
    expect(figure.textContent).toContain("…");
    expect(figure.textContent).toContain("<5>");
    expect(rankChart("R", [], fmt).querySelectorAll("rect")).toHaveLength(0);
    expect(rankChart("R", [{ label: "a", value: 1 }], fmt, 2).querySelector("rect")?.getAttribute("fill")).toBe(color(2));
  });

  it("draws intervals around a shared zero line", () => {
    const figure = intervalChart("I", [{ diff: 0.1, high: 0.3, label: "redo", low: -0.2 }], fmt);
    expect(figure.querySelector(".zero")).not.toBeNull();
    expect(figure.textContent).toContain("<0.1> [<-0.2>, <0.3>]");
    expect(intervalChart("I", [], fmt).querySelectorAll("circle")).toHaveLength(0);
  });
});

describe("format and columns", () => {
  it("formats every number kind and a missing value as a dash", () => {
    expect([usd(null), usd(undefined), usd(3), usd(250), share(null), share(undefined), share(0.25)]).toEqual(["—", "—", "$3.00", "$250", "—", "—", "25.0%"]);
    expect([compact(null), compact(undefined), compact(12), compact(1500), compact(2_500_000), compact(3_000_000_000)]).toEqual(["—", "—", "12", "1.5k", "2.5M", "3.0B"]);
    expect([duration(null), duration(undefined), duration(30), duration(300), duration(7500)]).toEqual(["—", "—", "30s", "5m", "2h 05m"]);
    expect([stamp(null), stamp(undefined)]).toEqual(["—", "—"]);
    expect(stamp(1_793_880_380)).toMatch(/^\d{4}-\d\d-\d\d \d\d:\d\d$/v);
    expect([cellText(null), cellText(""), cellText(2), cellText(2.345), cellText("s"), cellText(true), cellText(false), cellText({ a: 1 })]).toEqual(["—", "—", "2", "2.35", "s", "yes", "no", '{"a":1}']);
  });

  it("builds columns that show what their key says", () => {
    expect(col.text("a", "A", (value) => `x${String(value)}`).show?.(1, {})).toBe("x1");
    expect(col.text("a", "A").show).toBeUndefined();
    expect(col.money("a", "A").show?.(2, {})).toBe("$2.00");
  });

  it("infers columns by key name and value type", () => {
    const rows = [{ cost_usd: 1, n: 2, note: "a", run_s: 90, share: 0.5, tag: "x", tokens: 4000 }, { cost_usd: 2, n: 3, note: "a", run_s: 10, share: 0.1, tag: "y", tokens: 1 }];
    const kinds = Object.fromEntries(inferColumns(rows).map((column) => [column.key, column.kind]));
    expect(kinds).toEqual({ cost_usd: "number", n: "number", note: "text", run_s: "number", share: "number", tag: "enum", tokens: "number" });
    const shown = Object.fromEntries(inferColumns(rows).map((column) => [column.key, column.show?.(rows[0]?.[column.key as "n"], {})]));
    expect(shown.cost_usd).toBe("$1.00");
    expect(shown.share).toBe("50.0%");
    expect(shown.run_s).toBe("2m");
    expect(shown.tokens).toBe("4.0k");
    expect(shown.n).toBeUndefined();
    expect(inferColumns([])).toEqual([]);
  });
});
