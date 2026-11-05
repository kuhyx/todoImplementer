/** Chart geometry in a fixed viewBox, computed from data (jsdom has no layout). */
export const WIDTH = 520;
export const HEIGHT = 240;
export const MARGIN = { bottom: 30, left: 56, right: 14, top: 14 } as const;
export const PLOT_W = WIDTH - MARGIN.left - MARGIN.right;
export const PLOT_H = HEIGHT - MARGIN.top - MARGIN.bottom;

/** Order that passes the dataviz validator on both surfaces: CVD dE >= 12.9, contrast >= 3:1. */
export const SERIES_COLORS = ["var(--cat-2)", "var(--cat-3)", "var(--cat-5)", "var(--cat-4)", "var(--cat-1)"] as const;
export const color = (index: number): string => SERIES_COLORS[index % SERIES_COLORS.length] as string;

export function niceAxis(max: number, count = 4): { max: number; ticks: number[] } {
  const safe = max > 0 ? max : 1;
  const raw = safe / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 5].find((m) => m * magnitude >= raw) ?? 10) * magnitude;
  const top = Math.ceil(safe / step) * step;
  return { max: top, ticks: Array.from({ length: Math.round(top / step) + 1 }, (_, index) => index * step) };
}

export const scaleY = (value: number, max: number): number => MARGIN.top + PLOT_H - (value / max) * PLOT_H;

export const slotX = (index: number, count: number): number => MARGIN.left + ((index + 0.5) / count) * PLOT_W;

/** A null value breaks the line instead of drawing through zero. */
export function linePath(values: readonly (null | number)[], max: number): string {
  let isOpen = false;
  return values
    .map((value, index) => {
      if (value === null) {
        isOpen = false;
        return "";
      }
      const command = isOpen ? "L" : "M";
      isOpen = true;
      return `${command}${slotX(index, values.length).toFixed(1)} ${scaleY(value, max).toFixed(1)}`;
    })
    .join("");
}

export function labelIndexes(count: number, limit = 6): number[] {
  const every = Math.ceil(count / limit);
  return Array.from({ length: count }, (_, index) => index).filter((index) => index % every === 0);
}
