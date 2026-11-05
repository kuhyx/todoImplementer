import { describe, expect, it } from "vitest";

import { formatAgo, formatClock, formatIn, formatPercent, formatUsd, humanize } from "@/lib/format";

describe("format", () => {
  it("formats money and percent", () => {
    expect(formatUsd(12.3)).toBe("$12.30");
    expect(formatPercent(0.774)).toBe("77%");
  });

  it("formats elapsed time at every step", () => {
    expect(formatAgo(null, 100)).toBe("no activity yet");
    expect(formatAgo(98, 100)).toBe("just now");
    expect(formatAgo(40, 100)).toBe("1 min ago");
    expect(formatAgo(70, 100)).toBe("30 s ago");
    expect(formatAgo(0, 600)).toBe("10 min ago");
    expect(formatAgo(0, 7300)).toBe("2 h ago");
    expect(formatAgo(0, 200_000)).toBe("2 d ago");
    expect(formatAgo(500, 100)).toBe("just now");
  });

  it("formats time until a reset at every step", () => {
    expect(formatIn(100, 100)).toBe("now");
    expect(formatIn(100 + 1800, 100)).toBe("in 30 min");
    expect(formatIn(100 + 3 * 3600 + 120, 100)).toBe("in 3 h 2 min");
    expect(formatIn(100 + 3 * 86_400 + 7200, 100)).toBe("in 3 d 2 h");
  });

  it("formats a clock time in the given zone", () => {
    expect(formatClock(0, "UTC")).toBe("00:00");
    expect(formatClock(0)).toMatch(/^\d\d:\d\d$/v);
  });

  it("humanizes ids", () => {
    expect(humanize("needs_you")).toBe("Needs you");
    expect(humanize("lesson-approve")).toBe("Lesson approve");
  });
});
