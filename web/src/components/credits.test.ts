import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderCard } from "@/components/card";
import { renderUsage } from "@/components/usage-strip";
import { board as boardSchema, creditsFallbackResponse } from "@/lib/schemas";
import { ACTION_IDS } from "@/lib/schemas-common";
import { contractValidator } from "@/test/contract-ajv";
import { card, json, q } from "@/test/drawer-harness";
import { makeCredits } from "@/test/fixture-credits";
import { preset } from "@/test/fixture-presets";
import { makeBoard, NOW } from "@/test/fixtures";
import { settle, stubFetch } from "@/test/net";

const ready = makeCredits({ text: "Turns run on free API credits." });
const off = makeCredits({ enabled: false, route: "plan", state: "off", text: "Runs wait for the plan limit to end." });
const withCredits = (credits: typeof off) => ({ ...makeBoard(), limit: { active: false, credits, until: null } });
const mount = (board = makeBoard(), onCredits = vi.fn()): HTMLElement => {
  const element = renderUsage(null, board, null, null, NOW, onCredits);
  document.body.append(element);
  return element;
};

beforeEach(() => {
  vi.useFakeTimers();
  document.head.innerHTML = '<meta name="todoimpl-csrf" content="tok123">';
  document.body.replaceChildren();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("credits fallback toggle", () => {
  it("shows the server's label state and text", () => {
    mount(withCredits(off));
    expect(q("label.credits-label").textContent).toBe("Fall back to free API credits");
    expect(q<HTMLInputElement>("input[name=credits-fallback]").checked).toBe(false);
    expect(q(".credits-text").textContent).toBe(off.text);
  });

  it("POSTs the flipped value with the CSRF header, shows a loader after 1 s, then refreshes the board", async () => {
    const stub = stubFetch({
      "POST /api/settings/credits-fallback": async () => {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        return { credits: off, ok: true };
      },
    });
    const refresh = vi.fn();
    mount(withCredits(ready), refresh);
    q("input[name=credits-fallback]").click();
    const call = stub.calls[0];
    expect(call?.init?.body).toBe('{"enabled":false}');
    expect(call?.init?.headers).toMatchObject({ "X-Todoimpl-Token": "tok123" });
    expect(q<HTMLInputElement>("input[name=credits-fallback]").disabled).toBe(true);
    expect(document.querySelector(".loader")).toBeNull();
    await settle(1000);
    expect(q(".loader").textContent).toContain("Fall back to free API credits");
    await settle(600);
    expect(refresh).toHaveBeenCalledOnce();
    expect(q<HTMLInputElement>("input[name=credits-fallback]").disabled).toBe(false);
    expect(document.querySelector(".loader")).toBeNull();
  });

  it("shows the server's error text on failure and still refreshes", async () => {
    stubFetch({ "POST /api/settings/credits-fallback": () => json({ error: { code: "internal", message: "could not save" }, ok: false }, 500) });
    const refresh = vi.fn();
    mount(withCredits(off), refresh);
    q("input[name=credits-fallback]").click();
    await settle(0);
    expect(q(".credits-error").textContent).toBe("could not save");
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("the response mirror agrees with the contract", () => {
    for (const value of [{ credits: ready, ok: true }, { credits: { ...ready, state: "weird" }, ok: true }]) {
      expect(creditsFallbackResponse.safeParse(value).success).toBe(contractValidator("response")(value));
    }
  });
});

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
    for (const value of [{ ...makeBoard(), alert }, { ...makeBoard(), alert: { ...alert, kind: "other" } }]) {
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
