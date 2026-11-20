import { describe, expect, it } from "vitest";

import { renderCard } from "@/components/card";
import { renderUsage } from "@/components/usage-strip";
import { board as boardSchema } from "@/lib/schemas";
import { ACTION_IDS } from "@/lib/schemas-common";
import { contractValidator } from "@/test/contract-ajv";
import { card } from "@/test/drawer-harness";
import { preset } from "@/test/fixture-presets";
import { makeBoard, NOW } from "@/test/fixtures";

describe("route badge", () => {
  it("shows only for route credits, on the card", () => {
    const base = card("working");
    expect(renderCard({ ...base, route: "credits" }, NOW).querySelector(".route-chip")?.textContent).toBe("free credits");
    expect(renderCard({ ...base, route: "plan" }, NOW).querySelector(".route-chip")).toBeNull();
    expect(renderCard({ ...base, route: null }, NOW).querySelector(".route-chip")).toBeNull();
  });
});

describe("overage alert banner", () => {
  const alert = { kind: "overage" as const, text: "Overage guard stopped a turn spending extra usage.", until: NOW + 600 };

  it("renders the server's text as a red alert", () => {
    const banner = renderUsage(null, { ...makeBoard(), alert }, null, null, NOW).querySelector(".alert-banner");
    expect(banner?.textContent).toBe(alert.text);
    expect(banner?.getAttribute("role")).toBe("alert");
  });

  it("renders nothing when absent and the Zod mirror agrees with the contract", () => {
    expect(renderUsage(null, makeBoard(), null, null, NOW).querySelector(".alert-banner")).toBeNull();
    const relay = { ...alert, kind: "relay" as const, text: "Phone relay is off: no crdt-sync password" };
    expect(renderUsage(null, { ...makeBoard(), alert: relay }, null, null, NOW).querySelector(".alert-banner")?.getAttribute("data-kind")).toBe("relay");
    for (const value of [{ ...makeBoard(), alert }, { ...makeBoard(), alert: relay }, { ...makeBoard(), alert: { ...alert, kind: "other" } }]) {
      expect(boardSchema.safeParse(value).success).toBe(contractValidator("board")(value));
    }
  });
});

describe("credits action is gone", () => {
  it("is not an action id and no preset offers it", () => {
    expect(ACTION_IDS).not.toContain("credits");
    expect(preset("paused_limit", true).actions.map((action) => action.id)).not.toContain("credits");
  });
});
