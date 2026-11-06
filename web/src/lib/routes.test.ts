import { describe, expect, it } from "vitest";

import { routes } from "@/lib/routes";

describe("routes.shot", () => {
  it("[T1401] sends a nested live-check shot path relative to shots/, segment by segment", () => {
    expect(routes.shot("abcd1234-0", "shots/live2/v1-1366x768.png")).toBe("/api/task/abcd1234-0/shot/live2/v1-1366x768.png");
  });

  it("keeps a flat shot and encodes odd characters per segment", () => {
    expect(routes.shot("abcd1234-0", "shots/home.png")).toBe("/api/task/abcd1234-0/shot/home.png");
    expect(routes.shot("abcd1234-0", "live/a b.png")).toBe("/api/task/abcd1234-0/shot/live/a%20b.png");
  });
});
