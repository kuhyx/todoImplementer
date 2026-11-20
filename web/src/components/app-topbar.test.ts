/** The board's top bar (part 89abc8ca-2): the + sits in it, and search, repo and sort hide behind Advanced. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { defineApp, TiApp } from "@/components/app";
import { makeUsage } from "@/test/fixture-detail";
import { makeBoard } from "@/test/fixtures";
import { installEventSource, settle, stubFetch } from "@/test/net";

const q = <T extends Element = HTMLElement>(sel: string): T => {
  const element = document.querySelector<T>(sel);
  if (element === null) throw new Error(`no ${sel}`);
  return element;
};

async function mountApp(hash = ""): Promise<TiApp> {
  history.replaceState(null, "", `/${hash}`);
  stubFetch({ "GET /api/board": () => makeBoard(), "GET /api/usage": () => makeUsage() });
  const app = new TiApp();
  document.body.append(app);
  await settle(0);
  return app;
}

beforeEach(() => {
  vi.useFakeTimers();
  installEventSource();
  document.head.innerHTML = '<meta name="todoimpl-build" content="abc1234"><meta name="todoimpl-build-name" content="Radom"><meta name="todoimpl-csrf" content="tok">';
  document.body.replaceChildren();
  defineApp();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("board top bar", () => {
  it("puts the + in the top bar and hides search, repo and sort until Advanced opens them", async () => {
    await mountApp();
    expect(q(".usage-host ti-new-task [data-new-task=open]")).not.toBeNull();
    const advanced = q<HTMLButtonElement>(".usage-host [data-advanced]");
    expect(advanced.textContent).toBe("");
    expect(advanced.getAttribute("aria-label")).not.toBe("");
    expect(q(".toolbar").hidden).toBe(true);
    expect(advanced.getAttribute("aria-expanded")).toBe("false");
    advanced.click();
    expect(q(".toolbar").hidden).toBe(false);
    expect(advanced.getAttribute("aria-expanded")).toBe("true");
    await settle(3000);
    expect(q(".toolbar").hidden).toBe(false);
    advanced.click();
    expect(q(".toolbar").hidden).toBe(true);
  });

  it("opens Advanced by itself when the link already filters, so a filter is never invisible", async () => {
    await mountApp("#q=fix");
    expect(q(".toolbar").hidden).toBe(false);
    expect(q(".usage-host [data-advanced]").getAttribute("aria-expanded")).toBe("true");
  });

  it("names the build after its city, not its hash", async () => {
    await mountApp();
    expect(q(".usage-host .build").textContent).toBe("Radom");
  });
});
