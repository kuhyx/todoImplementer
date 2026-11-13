import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { pairResponse } from "@/phone/pair-api";
import { createPhoneTools, type PhoneTools } from "@/phone/phone-tools";
import { qrSvg } from "@/phone/qr";
import { settle, stubFetch } from "@/test/net";

const NOW = new Date("2026-11-13T12:00:00Z");
const seconds = (): number => Math.floor(Date.now() / 1000);
let tools: PhoneTools;

function mount(isLocal: boolean): void {
  document.head.innerHTML = `<meta name="todoimpl-csrf" content="tok">${isLocal ? '<meta name="todoimpl-local" content="1">' : ""}`;
  tools = createPhoneTools();
  document.body.append(tools.el);
}
const pairButton = (): HTMLButtonElement | null => document.querySelector('[data-phone="pair"]');
const q = <T extends Element = HTMLElement>(sel: string): T => {
  const found = document.querySelector<T>(sel);
  if (found === null) throw new Error(`no ${sel}`);
  return found;
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});

afterEach(() => {
  tools.dispose();
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("pair button", () => {
  it("is absent without the local meta and the tools stay hidden", () => {
    mount(false);
    expect(pairButton()).toBeNull();
    expect(tools.el.hidden).toBe(true);
  });

  it("is present with the local meta, named by title and aria-label only", () => {
    mount(true);
    expect(tools.el.hidden).toBe(false);
    expect(pairButton()?.title).toBe("Pair a phone");
    expect(pairButton()?.getAttribute("aria-label")).toBe("Pair a phone");
    expect(pairButton()?.textContent).toBe("");
  });

  it("mints with the CSRF header and shows the QR as an svg and the seconds left", async () => {
    const stub = stubFetch({ "POST /api/pair": () => ({ expires_at: seconds() + 300, url: "https://agents.kuhy.duckdns.org/pair?c=abc" }) });
    mount(true);
    pairButton()?.click();
    expect(q(".phone-spin")).toBeInTheDocument();
    await settle(0);
    const call = stub.calls[0];
    expect(call?.url).toBe("/api/pair");
    expect(call?.init?.method).toBe("POST");
    expect(call?.init?.headers).toMatchObject({ "X-Todoimpl-Token": "tok" });
    expect(q("svg.phone-qr path.qr-fg").getAttribute("d")).toMatch(/^M\d+ \d+h\d+v1h-\d+z/u);
    expect(q(".ring-digits").textContent).toBe("300");
    await settle(10_000);
    expect(q(".ring-digits").textContent).toBe("290");
    expect(q(".ring-arc").getAttribute("stroke-dashoffset")).not.toBe("0");
  });

  it("mints a new code when the shown one expires, and stops when closed", async () => {
    let n = 0;
    const stub = stubFetch({ "POST /api/pair": () => ({ expires_at: seconds() + 5, url: `https://x.test/pair?c=${String(++n)}` }) });
    mount(true);
    pairButton()?.click();
    await settle(0);
    const first = q("svg.phone-qr path.qr-fg").getAttribute("d");
    await settle(4000);
    expect(stub.calls).toHaveLength(1);
    await settle(1000);
    expect(stub.calls).toHaveLength(2);
    expect(q("svg.phone-qr path.qr-fg").getAttribute("d")).not.toBe(first);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await settle(30_000);
    expect(stub.calls).toHaveLength(2);
    expect(document.querySelector(".phone-backdrop")).toBeNull();
  });

  it("closes on the backdrop but not on a click inside the card, and ignores other keys", async () => {
    stubFetch({ "POST /api/pair": () => ({ expires_at: seconds() + 300, url: "https://x.test/pair?c=1" }) });
    mount(true);
    pairButton()?.click();
    await settle(0);
    q(".phone-card").click();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
    expect(document.querySelector(".phone-backdrop")).not.toBeNull();
    q(".phone-backdrop").click();
    expect(document.querySelector(".phone-backdrop")).toBeNull();
    expect(document.activeElement).toBe(pairButton());
  });

  it("a late answer after closing paints nothing, and closing twice is harmless", async () => {
    const pending = Promise.withResolvers<unknown>();
    stubFetch({ "POST /api/pair": () => pending.promise });
    mount(true);
    pairButton()?.click();
    q<HTMLButtonElement>('[data-phone="close"]').click();
    pending.resolve({ expires_at: seconds() + 300, url: "https://x.test/pair?c=1" });
    await settle(0);
    expect(document.querySelector(".phone-qr")).toBeNull();
  });

  it("a failed mint closed in flight paints no warning", async () => {
    const pending = Promise.withResolvers<unknown>();
    stubFetch({ "POST /api/pair": () => pending.promise });
    mount(true);
    pairButton()?.click();
    q<HTMLButtonElement>('[data-phone="close"]').click();
    pending.reject(new Error("late"));
    await settle(0);
    expect(document.querySelector(".phone-warn")).toBeNull();
  });

  it("a failed mint shows a warning glyph titled with the error; tapping it retries", async () => {
    let isFailing = true;
    const stub = stubFetch({
      "POST /api/pair": () => (isFailing ? new Response("no", { status: 403 }) : { expires_at: seconds() + 300, url: "https://x.test/pair?c=1" }),
    });
    mount(true);
    pairButton()?.click();
    await settle(0);
    const warn = q(".phone-warn");
    expect(warn.title).toBe("/api/pair: HTTP 403");
    expect(warn.getAttribute("aria-label")).toBe("/api/pair: HTTP 403");
    isFailing = false;
    warn.click();
    await settle(0);
    expect(stub.calls).toHaveLength(2);
    expect(document.querySelector(".phone-qr")).not.toBeNull();
  });

  it("reports a malformed answer and a missing page token", async () => {
    stubFetch({ "POST /api/pair": () => ({ url: 5 }) });
    mount(true);
    pairButton()?.click();
    await settle(0);
    expect(q(".phone-warn").title).toContain("unexpected shape");
    q(".phone-backdrop").click();
    document.head.innerHTML = '<meta name="todoimpl-local" content="1">';
    pairButton()?.click();
    await settle(0);
    expect(q(".phone-warn").title).toContain("no token");
  });
});

describe("pair contract and QR", () => {
  it("accepts exactly url and expires_at", () => {
    expect(pairResponse.safeParse({ expires_at: 1, url: "u" }).success).toBe(true);
    expect(pairResponse.safeParse({ expires_at: 1.5, url: "u" }).success).toBe(false);
    expect(pairResponse.safeParse({ expires_at: 1, extra: 1, url: "u" }).success).toBe(false);
  });

  it("draws one path sized by the version plus the quiet zone", () => {
    const svg = qrSvg("https://agents.kuhy.duckdns.org/pair?c=abcdefghijklmnop", "x");
    const size = Number(svg.getAttribute("viewBox")?.split(" ", 3)[2]);
    expect(size).toBeGreaterThan(8 + 21);
    expect(svg.querySelectorAll("path")).toHaveLength(1);
    expect(svg.getAttribute("aria-label")).toBe("x");
  });
});
