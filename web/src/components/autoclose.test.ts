import { describe, expect, it } from "vitest";

import { autoBadge, autoLine, renderCard } from "@/components/card";
import { renderHead } from "@/components/drawer-sections";
import { renderUsage } from "@/components/usage-strip";
import { board as boardSchema } from "@/lib/schemas";
import { taskCard } from "@/lib/schemas-common";
import { makeDetail } from "@/test/fixture-detail";
import { preset } from "@/test/fixture-presets";
import { makeBoard, makeCards, NOW } from "@/test/fixtures";

const base = makeCards()[0]!;
const closing = { ...base, ...preset("shipping", true), auto_start: { passed_at: NOW - 120, reason: "done_check" as const } };
const waiting = { ...base, auto: "waiting for a pass" };

describe("auto close on the board", () => {
  it("shows the server's auto note on a backlog card, word for word", () => {
    expect(taskCard.parse(waiting)).toEqual(waiting);
    const element = renderCard(waiting, NOW);
    expect(element.querySelector(".card-auto")?.textContent).toBe("auto: waiting for a pass");
    expect(renderCard(base, NOW).querySelector(".card-auto")).toBeNull();
  });

  it("[T2557] names the reset watch's token optimization run on the card and in the drawer", () => {
    const tokenopt = { ...base, ...preset("working", true), auto: "tokenopt" };
    expect(taskCard.parse(tokenopt)).toEqual(tokenopt);
    expect(renderCard(tokenopt, NOW).querySelector(".card-auto")?.textContent).toBe("auto: token optimization after reset");
    expect(renderHead(makeDetail(tokenopt)).querySelector(".drawer-auto")?.textContent).toBe("auto: token optimization after reset");
    expect(autoLine(base)).toBeNull();
  });

  it("badges a run a passing done_check started, with the pass time, and keeps it once done", () => {
    expect(taskCard.parse(closing)).toEqual(closing);
    const text = renderCard(closing, NOW).querySelector(".card-badge")?.textContent;
    expect(text).toMatch(/^auto: done_check passed at \d\d:\d\d$/v);
    const done = { ...closing, ...preset("done", true) };
    expect(renderCard(done, NOW).querySelector(".card-badge")?.textContent).toBe(text);
    expect(autoBadge(base)).toBeNull();
  });

  it("shows the badge and the auto note in the drawer head", () => {
    const head = renderHead(makeDetail(closing));
    expect(head.textContent).toContain("auto: done_check passed at");
    expect(renderHead(makeDetail(waiting)).querySelector(".drawer-auto")?.textContent).toBe("auto: waiting for a pass");
    expect(renderHead(makeDetail(base)).querySelector(".drawer-auto")).toBeNull();
  });

  it("keeps the auto_close flag in the board contract but shows no header switch (top bar, 2026-11-20)", () => {
    const off = makeBoard();
    expect(boardSchema.parse(off)).toEqual(off);
    expect(renderUsage(null, { ...off, auto_close: true }, null, null, NOW).querySelector(".auto-close")).toBeNull();
  });
});
