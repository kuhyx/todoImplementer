import { describe, expect, it } from "vitest";

import { STAGES } from "@/lib/schemas-common";
import { formatSpan, minutesUntil, restingStat, STAGE_ICON, stat } from "@/track/track-kit";

describe("formatSpan", () => {
  it("writes seconds, minutes, hours and days, and a dash for nothing measured", () => {
    expect(formatSpan(null)).toBe("–");
    expect(formatSpan(5.4)).toBe("5s");
    expect(formatSpan(59.6)).toBe("1m");
    expect(formatSpan(720)).toBe("12m");
    expect(formatSpan(5400)).toBe("1h 30m");
    expect(formatSpan(3 * 86_400 + 2 * 3600)).toBe("3d 2h");
  });
});

describe("minutesUntil", () => {
  it("rounds up and never goes negative", () => {
    expect(minutesUntil(1000, 940)).toBe(1);
    expect(minutesUntil(1000, 800)).toBe(4);
    expect(minutesUntil(1000, 2000)).toBe(0);
  });
});

describe("stat", () => {
  it("is an icon with a number, named in aria-label and title", () => {
    const element = stat("issue", "Issues", 3, { "data-x": "1" });
    expect(element.getAttribute("aria-label")).toBe("Issues 3");
    expect(element.title).toBe("Issues 3");
    expect(element.dataset.x).toBe("1");
    expect(element.querySelector(".t-num")?.textContent).toBe("3");
    expect(element.querySelector("svg")).not.toBeNull();
  });

  it("has no number element without a text", () => {
    const element = stat("free", "Free worker");
    expect(element.getAttribute("aria-label")).toBe("Free worker");
    expect(element.querySelector(".t-num")).toBeNull();
  });
});

describe("restingStat", () => {
  it("shows the reason icon and the minutes to the next try", () => {
    const element = restingStat({ kind: "network", until: 1300 }, 1000);
    expect(element.dataset.resting).toBe("network");
    expect(element.querySelector(".t-num")?.textContent).toBe("5m");
    expect(element.getAttribute("aria-label")).toContain("network");
  });

  it("has no countdown when the server gives no instant", () => {
    expect(restingStat({ kind: "limit", until: null }, 1000).querySelector(".t-num")).toBeNull();
  });
});

describe("STAGE_ICON", () => {
  it("has an icon for every stage in the contract enum", () => {
    for (const stage of STAGES) expect(STAGE_ICON[stage], stage).toBeTypeOf("string");
  });
});
