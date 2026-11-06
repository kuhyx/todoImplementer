/** The one-question view: typography structure, icon controls, no helper texts, no counter, inline code. */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { at, field, fresh, mount, q, useAskHarness } from "@/test/ask-harness";
import { ASK_ID, askDetail, askQuestions } from "@/test/fixture-ask";

useAskHarness();

const css = (name: string): string => readFileSync(join(import.meta.dirname, "..", "styles", `${name}.css`), "utf8");
const withBody = (body: string) => ({ ...askDetail(ASK_ID), questions: [{ ...askQuestions(1)[0]!, body }] });

describe("one-question view", () => {
  it("shows the title, body and answer only: no counter, no helper texts, no mode tabs", () => {
    const root = mount(fresh());
    expect(at()).toBe("Q1");
    expect(root?.querySelector(".ask-page, .ask-label, .ask-modes, .dtab")).toBeNull();
    expect(root?.textContent).not.toMatch(/\d \/ \d|Your answer|Recommended|One by one/v);
    expect(field().hasAttribute("aria-describedby")).toBe(false);
    expect(field().getAttribute("aria-label")).toBe("Answer to Q1");
  });

  it("puts a back arrow on the left and an OK check on the right, both icon-only and named", () => {
    mount(fresh());
    const [back, ok] = [...q(".ask-nav").children] as HTMLElement[];
    expect([back?.dataset.ask, ok?.dataset.ask]).toEqual(["back", "accept"]);
    for (const [button, name] of [[back, "Back"], [ok, "OK"]] as const) {
      expect(button?.getAttribute("aria-label")).toBe(name);
      expect(button?.title).toBe(name);
      expect(button?.textContent).toBe("");
      expect(button?.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
    }
  });

  it("renders `code` in the body and splits paragraphs on blank lines", () => {
    mount(fresh(), withBody("Run `make fast` first.\n\nThen `git push` is not allowed."));
    const paragraphs = document.querySelectorAll(".ask-body p");
    expect(paragraphs).toHaveLength(2);
    expect([...document.querySelectorAll(".ask-body code")].map((code) => code.textContent)).toEqual(["make fast", "git push"]);
    expect(paragraphs[0]?.textContent).toBe("Run make fast first.");
  });

  it("has a switch icon that flips between all questions and one at a time, kept out of the card", () => {
    mount(fresh());
    const switcher = q("[data-ask-mode]");
    expect([switcher.getAttribute("aria-label"), switcher.title, switcher.textContent]).toEqual(["All questions", "All questions", ""]);
    switcher.click();
    expect(switcher.getAttribute("aria-label")).toBe("One question at a time");
    expect(document.querySelectorAll(".ask-card textarea")).toHaveLength(5);
    expect(document.querySelectorAll(".ask-modes, [data-mode]")).toHaveLength(0);
    switcher.click();
    expect(switcher.getAttribute("aria-label")).toBe("All questions");
  });

  it("offers no switch before there are questions", () => {
    expect(fresh().switcher).toBeNull();
  });
});

describe("stylesheets", () => {
  const sheets = `${css("ask")}\n${css("drawer")}`;

  it("never truncates the task or question title", () => {
    expect(sheets).not.toMatch(/text-overflow|line-clamp|-webkit-box/v);
  });

  it("gives title, body and answer one font size and line height", () => {
    const ask = css("ask");
    expect(ask).toMatch(/\n\.ask\s*\{[^\}]*font-size: var\(--text-subtitle\)/v);
    expect(ask).toMatch(/\n\.ask\s*\{[^\}]*line-height: 1\.5/v);
    expect(ask).toMatch(/\.ask textarea\s*\{[^\}]*font: inherit/v);
    expect(ask).toMatch(/\.ask textarea\s*\{[^\}]*field-sizing: content/v);
    expect(ask).toMatch(/\.ask \.ask-title\s*\{[^\}]*font-size: inherit/v);
    expect(ask).toMatch(/\.ask \.ask-title\s*\{[^\}]*font-weight: 600/v);
    expect(ask).toMatch(/\.ask-body\s*\{[^\}]*gap: 1\.5lh/v);
    expect(ask).not.toMatch(/max-width: 52rem|\.ask-page|\.ask-label/v);
  });
});
