/** Number and time formatting shared by every usage view. The em dash stands for "no value". */
export const DASH = "—";

const BLANK = new Set<unknown>(["", null, undefined]);
const MINUTE = 60;
const HOUR = 3600;
const KILO = 1000;
const UNITS: readonly [number, string][] = [
  [KILO ** 3, "B"],
  [KILO ** 2, "M"],
  [KILO, "k"],
];

export function usd(value: null | number | undefined): string {
  if (value === null || value === undefined) return DASH;
  return value >= 100 ? `$${value.toFixed(0)}` : `$${value.toFixed(2)}`;
}

export function share(value: null | number | undefined): string {
  return value === null || value === undefined ? DASH : `${(value * 100).toFixed(1)}%`;
}

/** 12 345 -> "12.3k"; small numbers stay whole. */
export function compact(value: null | number | undefined): string {
  if (value === null || value === undefined) return DASH;
  const unit = UNITS.find(([size]) => Math.abs(value) >= size);
  return unit === undefined ? String(Math.round(value)) : `${(value / unit[0]).toFixed(1)}${unit[1]}`;
}

export function duration(seconds: null | number | undefined): string {
  if (seconds === null || seconds === undefined) return DASH;
  if (seconds < MINUTE) return `${String(Math.round(seconds))}s`;
  const minutes = Math.round(seconds / MINUTE);
  return seconds < HOUR ? `${String(minutes)}m` : `${String(Math.floor(minutes / MINUTE))}h ${String(minutes % MINUTE).padStart(2, "0")}m`;
}

/** Epoch seconds -> "2026-11-05 13:15" in local time. */
export function stamp(epoch: null | number | undefined): string {
  if (epoch === null || epoch === undefined) return DASH;
  const date = new Date(epoch * KILO);
  const part = (n: number): string => String(n).padStart(2, "0");
  return `${String(date.getFullYear())}-${part(date.getMonth() + 1)}-${part(date.getDate())} ${part(date.getHours())}:${part(date.getMinutes())}`;
}

/** Any cell -> display text. Objects print as JSON, never "[object Object]". */
export function cellText(value: unknown): string {
  if (BLANK.has(value)) return DASH;
  if (typeof value === "number") return Number.isSafeInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "yes" : "no";
  return JSON.stringify(value);
}
