/** The tracking view in the page: the link on the umbrella card and in the drawer, the route, Back, the routes helpers. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { defineApp, TiApp } from "@/components/app";
import { renderBoard } from "@/components/board-columns";
import { defineDrawer } from "@/components/drawer";
import { renderUmbrella } from "@/components/umbrella";
import { buildView } from "@/lib/board-model";
import { DEFAULT_STATE } from "@/lib/hash-state";
import { routes } from "@/lib/routes";
import { makeUsage } from "@/test/fixture-detail";
import { makeTrack, TRACK_ID } from "@/test/fixture-track";
import { makeBoard, makeCards, NOW } from "@/test/fixtures";
import { installEventSource, settle, stubFetch } from "@/test/net";
import { trackHref, trackLink } from "@/track/track-link";

const COUNTS = { done: 1, failed: 0, issues: 0, queued: 2, round: 1, running: 1, total: 4, width: 2 };

function cards() {
  const [first, ...rest] = makeCards();
  if (first === undefined) throw new Error("no fixture card");
  return [{ ...first, id: TRACK_ID, umbrella: COUNTS }, ...rest];
}

const q = <T extends Element = HTMLElement>(sel: string): T => {
  const found = document.querySelector<T>(sel);
  if (found === null) throw new Error(`no ${sel}`);
  return found;
};

describe("the link to the tracking view", () => {
  it("is a real anchor to #umbrella=<id> named for assistive tech", () => {
    const link = trackLink("#umbrella=2d0704cd-0");
    expect(link.getAttribute("href")).toBe("#umbrella=2d0704cd-0");
    expect(link.getAttribute("aria-label")).toBe(link.title);
    expect(link.querySelector("svg")).not.toBeNull();
  });

  it("keeps the board's filters in the href so Back returns to the same board", () => {
    expect(trackHref({ ...DEFAULT_STATE, repo: "utils", task: "17a1b2c3-0" }, TRACK_ID)).toBe("#repo=utils&umbrella=2d0704cd-0");
  });

  it("sits beside an umbrella card, not inside its button, and does not open the drawer", () => {
    const open = vi.fn();
    const board = makeBoard(cards());
    const root = renderBoard(buildView(board, DEFAULT_STATE), DEFAULT_STATE, NOW, { onColumn: vi.fn(), onOpen: open });
    document.body.replaceChildren(root);
    const link = q<HTMLAnchorElement>("a.card-track");
    expect(link.closest("button")).toBeNull();
    expect(link.getAttribute("href")).toBe(`#umbrella=${TRACK_ID}`);
    expect(link.parentElement?.className).toBe("card-wrap");
    link.addEventListener("click", (event) => { event.preventDefault(); });
    link.click();
    expect(open).not.toHaveBeenCalled();
    expect(document.querySelectorAll("a.card-track")).toHaveLength(1);
    expect(q(".card-wrap > button.card")).not.toBeNull();
  });

  it("is in the drawer's umbrella block too", () => {
    const block = renderUmbrella({ round: 0, rounds: [], rows: [], width: 1 }, TRACK_ID);
    expect(block.querySelector("a[data-track]")?.getAttribute("href")).toBe(`#umbrella=${TRACK_ID}`);
  });
});

describe("routes", () => {
  it("builds the umbrella and worker log urls", () => {
    expect(routes.umbrella(TRACK_ID)).toBe("/api/umbrella/2d0704cd-0");
    expect(routes.workerLog(TRACK_ID, "2d0704cd-3")).toBe("/api/umbrella/2d0704cd-0/log/2d0704cd-3");
    expect(routes.workerLog("a b", "c/d")).toBe("/api/umbrella/a%20b/log/c%2Fd");
  });
});

describe("ti-app with the tracking view", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-10T12:00:00Z"));
    installEventSource();
    document.head.innerHTML = '<meta name="todoimpl-build" content="abc1234"><meta name="todoimpl-csrf" content="tok">';
    document.body.replaceChildren();
    defineDrawer();
    defineApp();
  });

  afterEach(() => {
    document.body.replaceChildren();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    history.replaceState(null, "", "/");
  });

  async function mountApp(hash: string): Promise<TiApp> {
    history.replaceState(null, "", `/${hash}`);
    stubFetch({
      [`GET /api/umbrella/${TRACK_ID}`]: () => makeTrack(),
      "GET /api/board": () => makeBoard(cards()),
      "GET /api/usage": () => makeUsage(),
    });
    const app = new TiApp();
    document.body.append(app);
    await settle(0);
    return app;
  }

  it("shows the run instead of the board when the hash names an umbrella, usage strip kept", async () => {
    const app = await mountApp(`#umbrella=${TRACK_ID}`);
    expect(app.dataset.view).toBe("umbrella");
    expect(q("ti-track").hidden).toBe(false);
    expect(document.querySelectorAll("ti-track .t-kid")).toHaveLength(6);
    expect(q(".usage").textContent).toContain("Usage details");
  });

  it("opens the live feed of the umbrella card over the run", async () => {
    await mountApp(`#umbrella=${TRACK_ID}`);
    q<HTMLAnchorElement>('ti-track a[aria-label^="Live feed"]').click();
    history.replaceState(null, "", `/#umbrella=${TRACK_ID}&task=${TRACK_ID}`);
    globalThis.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(q("ti-drawer").hidden).toBe(false);
    expect(q("ti-app").dataset.view).toBe("umbrella");
  });

  it("goes back to the board when Back is pressed, and forward again from the card link", async () => {
    const app = await mountApp(`#umbrella=${TRACK_ID}`);
    q<HTMLButtonElement>("ti-track [data-close]").click();
    expect(location.hash).toBe("");
    expect(app.dataset.view).toBe("board");
    expect(q("ti-track").hidden).toBe(true);
    expect(document.querySelectorAll(".card").length).toBeGreaterThan(0);
    history.replaceState(null, "", `/${q<HTMLAnchorElement>("a.card-track").getAttribute("href") ?? ""}`);
    globalThis.dispatchEvent(new HashChangeEvent("hashchange"));
    expect(app.dataset.view).toBe("umbrella");
    await settle(0);
    expect(document.querySelectorAll("ti-track .t-kid")).toHaveLength(6);
  });

  it("stays on the board when the hash names no umbrella", async () => {
    const app = await mountApp("");
    expect(app.dataset.view).toBe("board");
    expect(q("ti-track").hidden).toBe(true);
    expect(q("ti-track").childElementCount).toBe(0);
  });
});
