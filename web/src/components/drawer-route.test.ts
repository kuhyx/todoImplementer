import { describe, expect, it } from "vitest";

import { card, open, q, useDrawerHarness } from "@/test/drawer-harness";

useDrawerHarness();

describe("drawer route badge", () => {
  it("shows free credits in the header only for route credits", async () => {
    await open({ ...card("working"), route: "credits" });
    expect(q(".drawer-chips").textContent).toContain("free credits");
    await open({ ...card("working"), route: "plan" });
    expect(q(".drawer-chips").textContent).not.toContain("free credits");
  });
});
