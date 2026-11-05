/** Pure display formatters. `now` is always passed in so tests need no clock. */

export function formatUsd(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

export function formatPercent(fraction: number): string {
  return `${String(Math.round(fraction * 100))}%`;
}

export function formatAgo(epoch: null | number, now: number): string {
  if (epoch === null) return "no activity yet";
  const seconds = Math.max(0, Math.round(now - epoch));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${String(seconds)} s ago`;
  if (seconds < 3600) return `${String(Math.floor(seconds / 60))} min ago`;
  return seconds < 86_400 ? `${String(Math.floor(seconds / 3600))} h ago` : `${String(Math.floor(seconds / 86_400))} d ago`;
}

export function formatIn(epoch: number, now: number): string {
  const minutes = Math.max(0, Math.round((epoch - now) / 60));
  if (minutes < 1) return "now";
  if (minutes < 60) return `in ${String(minutes)} min`;
  const hours = Math.floor(minutes / 60);
  return hours < 48 ? `in ${String(hours)} h ${String(minutes % 60)} min` : `in ${String(Math.floor(hours / 24))} d ${String(hours % 24)} h`;
}

export function formatClock(epoch: number, timeZone?: string): string {
  const options: Intl.DateTimeFormatOptions = { hour: "2-digit", hour12: false, minute: "2-digit" };
  if (timeZone !== undefined) options.timeZone = timeZone;
  const formatter = new Intl.DateTimeFormat("en-GB", options);
  return formatter.format(new Date(epoch * 1000));
}

/** "needs_you" -> "Needs you"; used only for enum ids the server sends. */
export function humanize(id: string): string {
  const spaced = id.replaceAll(/[_\-]/gv, " ");
  return spaced.slice(0, 1).toUpperCase() + spaced.slice(1);
}
