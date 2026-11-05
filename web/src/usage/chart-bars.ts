import { axes, emptyPlot, frame, type Series } from "@/usage/chart-frame";
import { plainFigure } from "@/usage/chart-frame";
import { color,  MARGIN, niceAxis, PLOT_W, scaleY, slotX, WIDTH } from "@/usage/chart-scale";
import { svg } from "@/usage/svg";

export interface BarOptions {
  fmt: (value: number) => string;
  labels: string[];
  series: Series[];
  title: string;
}

const TOP_RADIUS = 4;

/** Stacked bars on one axis, a 2px surface gap between fills, a rounded data end anchored to the baseline. */
export function barChart(options: BarOptions): HTMLElement {
  const { fmt, labels, series, title } = options;
  const totals = labels.map((_, index) => series.reduce((sum, s) => sum + (s.values[index] ?? 0), 0));
  const max = niceAxis(Math.max(0, ...totals)).max;
  const width = Math.min(28, (PLOT_W / Math.max(labels.length, 1)) * 0.7);
  const plot = emptyPlot();
  plot.append(axes(max, labels, fmt));
  for (const index of labels.keys()) {
    let base = 0;
    for (const s of series) {
      const value = s.values[index] ?? 0;
      if (value <= 0) continue;
      const top = scaleY(base + value, max);
      const height = scaleY(base, max) - top;
      plot.append(svg("rect", { class: "bar", fill: s.color, height: Math.max(height, 1), rx: Math.min(TOP_RADIUS, height / 2), stroke: "var(--surface-1)", "stroke-width": 2, width, x: slotX(index, labels.length) - width / 2, y: top }));
      base += value;
    }
  }
  return frame(title, plot, labels, series, fmt).figure;
}

export interface RankRow {
  label: string;
  value: number;
}

const ROW = 28;
const LABEL_W = 150;
const VALUE_W = 70;

/** Horizontal ranked bars with the value printed at the bar end (direct labels, so no legend and no tooltip). */
export function rankChart(title: string, rows: readonly RankRow[], fmt: (value: number) => string, index = 0): HTMLElement {
  const max = Math.max(0, ...rows.map((r) => r.value)) || 1;
  const span = WIDTH - LABEL_W - VALUE_W;
  const plot = svg("svg", { class: "plot", role: "img", viewBox: `0 0 ${String(WIDTH)} ${String(rows.length * ROW + MARGIN.top)}` });
  for (const [at, row] of rows.entries()) {
    const y = at * ROW + MARGIN.top;
    const length = Math.max((row.value / max) * span, 1);
    plot.append(
      svg("text", { class: "tick", "text-anchor": "end", x: LABEL_W - 8, y: y + 14 }, row.label.length > 22 ? `${row.label.slice(0, 21)}…` : row.label),
      svg("rect", { class: "bar", fill: color(index), height: 16, rx: 4, width: length, x: LABEL_W, y: y + 2 }),
      svg("text", { class: "tick", x: LABEL_W + length + 6, y: y + 14 }, fmt(row.value)),
    );
  }
  return plainFigure(title, plot);
}



