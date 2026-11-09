import { describe, expect, it, vi } from "vitest";

import { idleBar, renderAction } from "@/components/action-bar";
import { autoBadge, renderCard, statusChip } from "@/components/card";
import { renderHead } from "@/components/drawer-sections";
import { renderUsage } from "@/components/usage-strip";
import { board as boardSchema } from "@/lib/schemas";
import { taskCard } from "@/lib/schemas-common";
import { makeDetail } from "@/test/fixture-detail";
import { preset } from "@/test/fixture-presets";
import { makeBoard, makeCards, NOW } from "@/test/fixtures";

const base = makeCards()[0]!;
const closing = { ...base, ...preset("ready_to_close", true), auto_start: { passed_at: NOW - 120, reason: "done_check" as const } };
const waiting = { ...base, auto: "waiting for a pass" };

describe("auto close on the board", () => {
  it("shows the server's auto note on a backlog card, word for word", () => {
    expect(taskCard.parse(waiting)).toEqual(waiting);
    const element = renderCard(waiting, NOW);
    expect(element.querySelector(".card-auto")?.textContent).toBe("auto: waiting for a pass");
    expect(renderCard(base, NOW).querySelector(".card-auto")).toBeNull();
  });

  it("badges a run a passing done_check started, with the pass time, and keeps it once done", () => {
    expect(taskCard.parse(closing)).toEqual(closing);
    const text = renderCard(closing, NOW).querySelector(".card-badge")?.textContent;
    expect(text).toMatch(/^auto: done_check passed at \d\d:\d\d$/v);
    const done = { ...closing, ...preset("done", true) };
    expect(renderCard(done, NOW).querySelector(".card-badge")?.textContent).toBe(text);
    expect(autoBadge(base)).toBeNull();
    expect(statusChip("ready_to_close").textContent).toBe("Ready to close");
  });

  it("shows the badge and the auto note in the drawer head", () => {
    const head = renderHead(makeDetail(closing));
    expect(head.textContent).toContain("auto: done_check passed at");
    expect(renderHead(makeDetail(waiting)).querySelector(".drawer-auto")?.textContent).toBe("auto: waiting for a pass");
    expect(renderHead(makeDetail(base)).querySelector(".drawer-auto")).toBeNull();
  });

  it("offers Close as the primary button and never Ship on a Ready-to-close card", () => {
    const ids = closing.actions.map((action) => action.id);
    expect(ids).toContain("close");
    expect(ids).not.toContain("ship");
    const host = { activate: vi.fn(), cancelConfirm: vi.fn(), state: idleBar };
    const close = closing.actions.find((action) => action.id === "close")!;
    const element = renderAction(close, host, closing.id);
    expect(element.querySelector("button")?.className).toContain("primary");
  });

  it("names the switch in the header from the board's auto_close flag", () => {
    const off = makeBoard();
    expect(boardSchema.parse(off)).toEqual(off);
    expect(renderUsage(null, off, null, null, NOW).querySelector(".auto-close")?.textContent).toBe("auto close: off");
    const on = { ...off, auto_close: true };
    expect(renderUsage(null, on, null, null, NOW).querySelector(".auto-close")?.textContent).toBe("auto close: on");
    expect(renderUsage(null, null, null, null, NOW).querySelector(".auto-close")).toBeNull();
  });
});
