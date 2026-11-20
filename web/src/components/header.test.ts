/** The compact top bar (part 89abc8ca-2): one row of build name, 7 d meter, free left/used, credits bar and links. */
import { describe, expect, it } from "vitest";

import { renderFree } from "@/components/free-strip";
import { renderUsage } from "@/components/usage-strip";
import { makeUsage } from "@/test/fixture-detail";
import { makeFree } from "@/test/fixture-free";
import { makeBoard, NOW } from "@/test/fixtures";

const top = (): HTMLElement => renderUsage(makeUsage(), makeBoard(), null, "Radom", NOW);

describe("top bar", () => {
  it("drops the title, Running, auto close, Today, the 5 h meter and the fall-back switch", () => {
    const bar = top();
    const text = bar.textContent;
    expect(bar.querySelector(".brand, .slots, .auto-close, .today, .credits-toggle")).toBeNull();
    for (const gone of ["todoImplementer", "Running", "auto close", "Today", "5 h", "Fall back"]) expect(text).not.toContain(gone);
  });

  it("keeps everything else on one row: build name, 7 d meter, free strip, credits bar, usage link and terminal", () => {
    const bar = top();
    const rows = bar.querySelectorAll(".usage-row");
    expect(rows).toHaveLength(1);
    const row = rows[0];
    for (const sel of [".build", ".meter-box", ".free-strip", ".credits-pace", ".usage-link", ".sessions-link"]) expect(row?.querySelector(sel)).not.toBeNull();
    expect(row?.querySelector(".build")?.textContent).toBe("Radom");
    expect(row?.querySelector(".meter-label")?.textContent).toBe("7 d");
  });
});

describe("free strip", () => {
  it("shows only what is left and what was used, as numbers", () => {
    const strip = renderFree(makeFree(), NOW);
    expect([...strip.querySelectorAll<HTMLElement>("[data-kind]")].map((chip) => chip.dataset.kind)).toEqual(["left", "used"]);
    expect(strip.querySelector('[data-kind="left"]')?.textContent).toBe("89");
    expect(strip.querySelector('[data-kind="used"]')?.textContent).toBe("812k");
    expect(strip.querySelector('[data-kind="left"]')?.getAttribute("title")).toContain("left");
  });

  it("shows nothing but a dash per figure when the gateway was never read or has no figures", () => {
    for (const free of [undefined, { ...makeFree(), quotas: [], tokens: null }]) {
      const strip = renderFree(free, NOW);
      expect([...strip.querySelectorAll("[data-kind]")].map((chip) => chip.textContent)).toEqual(["-", "-"]);
    }
  });

  it("counts every client's tokens when the gateway does not split out ours", () => {
    const free = makeFree();
    const strip = renderFree({ ...free, tokens: { in: 1000, ours: null, out: 500, requests: 3 } }, NOW);
    expect(strip.querySelector('[data-kind="used"]')?.textContent).toBe("2k");
  });
});
