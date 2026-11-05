import { plainFigure } from "@/usage/chart-frame";
import { WIDTH } from "@/usage/chart-scale";
import { svg } from "@/usage/svg";

export interface Interval {
  diff: number;
  high: number;
  label: string;
  low: number;
}

const ROW = 36;
const LABEL_W = 110;
const TOP = 26;

/** Difference with its confidence interval per measure, on one shared axis with a zero line. */
export function intervalChart(title: string, rows: readonly Interval[], fmt: (value: number) => string): HTMLElement {
  const reach = Math.max(0.0001, ...rows.flatMap((r) => [Math.abs(r.low), Math.abs(r.high)]));
  const span = WIDTH - LABEL_W - 190;
  const x = (value: number): number => LABEL_W + span / 2 + (value / reach) * (span / 2);
  const plot = svg("svg", { class: "plot", role: "img", viewBox: `0 0 ${String(WIDTH)} ${String(rows.length * ROW + TOP)}` });
  plot.append(svg("line", { class: "zero", x1: x(0), x2: x(0), y1: 6, y2: rows.length * ROW + 10 }), svg("text", { class: "tick", "text-anchor": "middle", x: x(0), y: 4 }, "0"));
  for (const [index, row] of rows.entries()) {
    const y = TOP + index * ROW;
    plot.append(
      svg("text", { class: "tick", "text-anchor": "end", x: LABEL_W - 8, y: y + 4 }, row.label),
      svg("line", { class: "ci", stroke: "var(--cat-2)", "stroke-width": 2, x1: x(row.low), x2: x(row.high), y1: y, y2: y }),
      svg("circle", { class: "marker", cx: x(row.diff), cy: y, fill: "var(--cat-2)", r: 5, stroke: "var(--surface-1)", "stroke-width": 2 }),
      svg("text", { class: "tick", x: LABEL_W + span + 12, y: y + 4 }, `${fmt(row.diff)} [${fmt(row.low)}, ${fmt(row.high)}]`),
    );
  }
  return plainFigure(title, plot);
}
