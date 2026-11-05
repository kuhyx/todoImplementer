import { afterEach, describe, expect, it, vi } from "vitest";

import { renderBoard } from "@/components/board-columns";
import { buildView } from "@/lib/board-model";
import { DEFAULT_STATE, parseHash } from "@/lib/hash-state";
import { makeBoard, makeCards, NOW } from "@/test/fixtures";

const draw = (columns: string[], hash: string): null | string => {
  const board = makeBoard(makeCards().filter((card) => columns.includes(card.column)));
  const state = parseHash(hash);
  const root = renderBoard(buildView(board, state), state, NOW, { onColumn: vi.fn(), onOpen: vi.fn() });
  document.body.replaceChildren(root);
  const tab = root.querySelector('.tab[aria-current="true"]')?.getAttribute("data-col") ?? null;
  expect(root.querySelector(".col[data-active]")?.getAttribute("data-col")).toBe(tab);
  return tab;
};

afterEach(() => {
  document.body.replaceChildren();
});

describe("active column with no tab in the hash", () => {
  it("[T601] opens the first non-empty column when Needs you is empty", () => {
    expect(draw(["backlog", "done"], "")).toBe("backlog");
    expect(draw(["ready", "done"], "")).toBe("ready");
  });

  it("prefers Needs you when it has cards, and Backlog when the board is empty", () => {
    expect(draw(["backlog", "needs_you"], "")).toBe("needs_you");
    expect(draw([], "")).toBe("backlog");
  });

  it("lets an explicit hash choice win, even on an empty column", () => {
    expect(draw(["backlog"], "#col=needs_you")).toBe("needs_you");
    expect(draw(["backlog", "ready"], "#col=ready")).toBe("ready");
  });

  it("leaves the chosen column out of the default hash state", () => {
    expect(DEFAULT_STATE.col).toBeNull();
  });
});
