/** Everything around a plot: title, legend (2+ series), axes, hover layer (crosshair + tooltip) and the table view. */
import { h } from "@/lib/dom";
import { HEIGHT, labelIndexes, MARGIN, niceAxis, PLOT_H, PLOT_W, scaleY, slotX, WIDTH } from "@/usage/chart-scale";
import { label } from "@/usage/labels";
import { svg } from "@/usage/svg";

export interface Series {
  color: string;
  name: string;
  values: (null | number)[];
}

export interface Frame {
  figure: HTMLElement;
  plot: SVGSVGElement;
}

const text = (content: string, attributes: Record<string, number | string>): SVGTextElement => svg("text", attributes, content);

function legend(series: readonly Series[]): HTMLElement | null {
  return series.length < 2 ? null : h("ul", { class: "legend" }, ...series.map((s) => h("li", {}, svg("svg", { "aria-hidden": "true", height: 10, width: 14 }, svg("rect", { fill: s.color, height: 10, rx: 2, width: 14 })), s.name)));
}

/** Grid + y labels + x labels for a vertical value axis. */
export function axes(max: number, labels: readonly string[], fmt: (value: number) => string): SVGGElement {
  const group = svg("g", { class: "axes" });
  for (const tick of niceAxis(max).ticks) {
    const y = scaleY(tick, max);
    group.append(svg("line", { class: "grid", x1: MARGIN.left, x2: WIDTH - MARGIN.right, y1: y, y2: y }), text(fmt(tick), { class: "tick", "text-anchor": "end", x: MARGIN.left - 6, y: y + 4 }));
  }
  const printed = new Set(labelIndexes(labels.length));
  for (const [index, name] of labels.entries()) {
    if (printed.has(index)) group.append(text(name, { class: "tick", "text-anchor": "middle", x: slotX(index, labels.length), y: HEIGHT - 8 }));
  }
  return group;
}

/** Table view of the same numbers: the accessible twin of every chart. */
function tableView(labels: readonly string[], series: readonly Series[], fmt: (value: number) => string): HTMLElement {
  const head = h("tr", {}, h("th", { text: "" }), ...series.map((s) => h("th", { text: s.name })));
  const rows = labels.map((name, index) => h("tr", {}, h("th", { text: name }), ...series.map((s) => h("td", { class: "num", text: s.values[index] == null ? "—" : fmt(s.values[index]) }))));
  return h("details", { class: "chart-table" }, h("summary", { text: label.table }), h("div", { class: "ut-scroll" }, h("table", {}, h("thead", {}, head), h("tbody", {}, ...rows))));
}

/**
 * Wraps `plot` in a figure and wires hover: one hit rect per slot moves the crosshair and fills the tooltip.
 * Position is set through CSSOM (allowed under the CSP), as a percentage so it survives scaling.
 */
export function frame(title: string, plot: SVGSVGElement, labels: readonly string[], series: readonly Series[], fmt: (value: number) => string): Frame {
  const tip = h("div", { attrs: { role: "status" }, class: "tip" });
  tip.hidden = true;
  const cross = svg("line", { class: "cross", y1: MARGIN.top, y2: MARGIN.top + PLOT_H });
  cross.setAttribute("visibility", "hidden");
  const slot = PLOT_W / Math.max(labels.length, 1);
  const show = (index: number, name: string): void => {
    const x = slotX(index, labels.length);
    cross.setAttribute("x1", String(x));
    cross.setAttribute("x2", String(x));
    cross.setAttribute("visibility", "visible");
    tip.replaceChildren(h("strong", { text: name }), ...series.map((s) => h("div", {}, h("span", { attrs: { "data-c": s.name }, class: "swatch" }), `${s.name}: ${s.values[index] == null ? "—" : fmt(s.values[index])}`)));
    tip.hidden = false;
    tip.style.left = `${((x / WIDTH) * 100).toFixed(1)}%`;
  };
  const hide = (): void => {
    cross.setAttribute("visibility", "hidden");
    tip.hidden = true;
  };
  const hits = labels.map((name, index) => {
    const rect = svg("rect", { "aria-label": name, class: "hit", fill: "transparent", height: PLOT_H, tabindex: 0, width: slot, x: slotX(index, labels.length) - slot / 2, y: MARGIN.top });
    for (const event of ["mouseenter", "focus"]) rect.addEventListener(event, () => { show(index, name); });
    for (const event of ["mouseleave", "blur"]) rect.addEventListener(event, hide);
    return rect;
  });
  plot.append(cross, ...hits);
  const figure = h("figure", { class: "chart" }, h("figcaption", { text: title }), legend(series), h("div", { class: "chart-box" }, plot, tip), tableView(labels, series, fmt));
  return { figure, plot };
}

export function emptyPlot(): SVGSVGElement {
  return svg("svg", { class: "plot", preserveAspectRatio: "xMidYMid meet", role: "img", viewBox: `0 0 ${String(WIDTH)} ${String(HEIGHT)}` });
}

export function plainFigure(title: string, plot: SVGSVGElement): HTMLElement {
  return h("figure", { class: "chart" }, h("figcaption", { text: title }), plot);
}
