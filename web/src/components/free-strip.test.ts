import { describe, expect, it } from "vitest";

import { renderFree } from "@/components/free-strip";
import { renderUsage } from "@/components/usage-strip";
import { makeUsage } from "@/test/fixture-detail";
import { makeFree } from "@/test/fixture-free";
import { NOW } from "@/test/fixtures";

const kind = (root: HTMLElement, name: string): HTMLElement | null => root.querySelector(`[data-kind="${CSS.escape(name)}"]`);
const visibleText = (root: HTMLElement): string => root.textContent;

describe("free-model strip", () => {
  it("shows the grey gateway icon alone when nothing was read", () => {
    const strip = renderFree(undefined, NOW);
    expect(strip.querySelectorAll(".f-chip")).toHaveLength(1);
    expect(kind(strip, "gateway")?.dataset.tone).toBe("unknown");
    expect(strip.dataset.state).toBe("unknown");
    expect(kind(strip, "gateway")?.title).toContain("not read yet");
  });

  it("shows the same alone while the state is unknown even with figures", () => {
    const strip = renderFree({ ...makeFree(), state: "unknown" }, NOW);
    expect(strip.querySelectorAll(".f-chip")).toHaveLength(1);
  });

  it("carries only numbers as visible text, never words", () => {
    expect(visibleText(renderFree(makeFree(), NOW))).toMatch(/^[\d.kM]+$/v);
  });

  it("counts providers by state with icons and names them in the tooltips", () => {
    const strip = renderFree(makeFree(), NOW);
    expect(kind(strip, "ok")?.textContent).toBe("2");
    expect(kind(strip, "cooling")?.textContent).toBe("1");
    expect(kind(strip, "cooling")?.title).toMatch(/^Cooling down: groq until \d\d:\d\d$/v);
    expect(kind(strip, "failing")?.textContent).toBe("2");
    expect(kind(strip, "failing")?.title).toBe("Failing or off: xkiro, agnes");
  });

  it("names a cooling provider without a cooldown end by its id alone", () => {
    const free = makeFree();
    free.providers = free.providers.map((p) => (p.state === "cooling" ? { ...p, until: null } : p));
    expect(kind(renderFree(free, NOW), "cooling")?.title).toBe("Cooling down: groq");
  });

  it("hides the cooling and failing counts when none is cooling or failing", () => {
    const free = { ...makeFree(), counts: { cooling: 0, failing: 0, ok: 5, providers: 5, quota_known: 1 }, models: { cooling: 0, total: 3 } };
    const strip = renderFree(free, NOW);
    expect(kind(strip, "cooling")).toBeNull();
    expect(kind(strip, "failing")).toBeNull();
    expect(kind(strip, "models")).toBeNull();
  });

  it("draws one meter per quota with a tone by the share left", () => {
    const meters = [...renderFree(makeFree(), NOW).querySelectorAll<HTMLElement>(".f-meter")];
    expect(meters.map((m) => m.dataset.tone)).toEqual(["danger", "warn", "ok"]);
    expect(meters.map((m) => m.getAttribute("aria-valuenow"))).toEqual(["8", "25", "80"]);
    expect(meters[0]?.querySelector<HTMLElement>(".f-meter-fill")?.style.getPropertyValue("--fill")).toBe("8%");
    expect(meters[0]?.title).toMatch(/^openrouter free_daily: 4 of 50 left, resets \d\d:\d\d$/v);
    expect(meters[1]?.title).toBe("openrouter free_rpm: 5 of 20 left");
  });

  it("draws no quota group when no provider reports a limit", () => {
    const strip = renderFree({ ...makeFree(), quotas: [] }, NOW);
    expect(strip.querySelector(".f-meter")).toBeNull();
  });

  it("shows tokens today compactly, gateway-wide and ours apart", () => {
    const strip = renderFree(makeFree(), NOW);
    expect(kind(strip, "tokens")?.textContent).toBe("4.0M");
    expect(kind(strip, "tokens")?.title).toContain("4000000 in, 20000 out, 163 requests");
    expect(kind(strip, "ours")?.textContent).toBe("812k");
  });

  it("leaves out our share when no worker ran today and all tokens when unread", () => {
    const free = makeFree();
    free.tokens = { ...(free.tokens ?? { in: 0, out: 0, requests: 0 }), in: 10, ours: null, out: 5, requests: 1 };
    const strip = renderFree(free, NOW);
    expect(kind(strip, "ours")).toBeNull();
    expect(kind(strip, "tokens")?.textContent).toBe("15");
    expect(kind(renderFree({ ...makeFree(), tokens: null }, NOW), "tokens")).toBeNull();
  });

  it("draws the chain as dots in order, colored by state, each with its tooltip", () => {
    const dots = [...renderFree(makeFree(), NOW).querySelectorAll<HTMLElement>(".f-dot")];
    expect(dots.map((d) => d.dataset.state)).toEqual(["ok", "cooling", "failing"]);
    expect(dots[0]?.title).toBe("nvidia nvidia/nemotron 100%, 48 requests (ok)");
    expect(dots[1]?.title).toBe("groq groq/compound no calls, 0 requests (cooling)");
  });

  it("draws no chain without a combo", () => {
    expect(renderFree({ ...makeFree(), combo: null }, NOW).querySelector(".f-chain")).toBeNull();
  });

  it("shows the models cooling count only when above zero", () => {
    expect(kind(renderFree(makeFree(), NOW), "models")?.textContent).toBe("1");
  });

  it.each([
    ["ok", "ok"],
    ["stale", "warn"],
    ["down", "danger"],
  ] as const)("tones the gateway icon %s -> %s and says why", (state, tone) => {
    const strip = renderFree({ ...makeFree(), error: "combos: HTTP 401", state }, NOW);
    const gateway = kind(strip, "gateway");
    expect(gateway?.dataset.tone).toBe(tone);
    expect(gateway?.title).toContain("read 12 s ago");
    expect(gateway?.title).toContain("(combos: HTTP 401)");
  });

  it("says nothing of age when the gateway was never read", () => {
    const strip = renderFree({ ...makeFree(), at: null, error: null, state: "down" }, NOW);
    expect(kind(strip, "gateway")?.title).toBe("Free-model gateway: unreachable, last reading shown");
  });

  it("sits in the usage strip next to the plan meters", () => {
    const host = renderUsage(makeUsage(), null, null, null, NOW);
    const row = host.querySelector(".free-strip")?.parentElement;
    expect(row?.querySelectorAll(".meter-box")).toHaveLength(2);
    const bare = renderUsage({ ...makeUsage(), free: undefined }, null, null, null, NOW);
    expect(bare.querySelector(".free-strip")?.getAttribute("data-state")).toBe("unknown");
  });
});
