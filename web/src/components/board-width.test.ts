import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";

import { renderBoard } from "@/components/board-columns";
import { buildView } from "@/lib/board-model";
import { DEFAULT_STATE } from "@/lib/hash-state";
import { makeBoard, NOW } from "@/test/fixtures";

const css = readFileSync(join(import.meta.dirname, "../styles/board.css"), "utf8");

describe("board width", () => {
  it("[T2077] the columns and tabs are laid out by the real column count, so no strip stays empty on the right", () => {
    const view = buildView(makeBoard(), DEFAULT_STATE);
    const board = renderBoard(view, DEFAULT_STATE, NOW, { onColumn: vi.fn(), onOpen: vi.fn() });
    for (const selector of [".cols", ".tabs"]) {
      const row = board.querySelector<HTMLElement>(selector);
      expect(row?.style.getPropertyValue("--cols")).toBe(String(view.length));
    }
    expect(css).not.toMatch(/repeat\(\s*\d/u); // a fixed count (five before the Ready to ship column went) leaves a gap
    expect(css.match(/repeat\(var\(--cols\)/gu)).toHaveLength(2);
  });
});
