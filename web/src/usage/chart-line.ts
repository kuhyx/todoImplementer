import { axes, emptyPlot, frame, type Series } from "@/usage/chart-frame";
import { linePath, niceAxis, scaleY, slotX } from "@/usage/chart-scale";
import { svg } from "@/usage/svg";

export interface LineOptions {
  fmt: (value: number) => string;
  labels: string[];
  series: Series[];
  title: string;
}

const MARKER_MAX = 14;

/** 2px lines, 8px markers with a surface ring (only while points are sparse), hover crosshair, legend for 2+ series. */
export function lineChart(options: LineOptions): HTMLElement {
  const { fmt, labels, series, title } = options;
  const max = niceAxis(Math.max(0, ...series.flatMap((s) => s.values.filter((v): v is number => v !== null)))).max;
  const plot = emptyPlot();
  plot.append(axes(max, labels, fmt));
  for (const s of series) {
    plot.append(svg("path", { class: "line", d: linePath(s.values, max), fill: "none", stroke: s.color, "stroke-linejoin": "round", "stroke-width": 2 }));
    if (labels.length > MARKER_MAX) continue;
    for (const [index, value] of s.values.entries()) {
      if (value !== null) plot.append(svg("circle", { class: "marker", cx: slotX(index, labels.length), cy: scaleY(value, max), fill: s.color, r: 4 }));
    }
  }
  return frame(title, plot, labels, series, fmt).figure;
}
