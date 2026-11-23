import { describe, expect, it } from "vitest";

import { h } from "@/lib/dom";
import { inline, renderMarkdown } from "@/lib/markdown";

const html = (text: string): string => h("p", {}, ...inline(text)).outerHTML.slice("<p>".length, -"</p>".length);

describe("inline", () => {
  it("[T2525] renders **bold** as <strong>, beside `code`, with no raw stars", () => {
    expect(html("❓ **Q1 - Queued note**: run `make fast` first")).toBe(
      "❓ <strong>Q1 - Queued note</strong>: run <code>make fast</code> first",
    );
  });

  it("[T2525] leaves a lone ** and escapes markup inside bold", () => {
    expect(html("2 ** 3 and **<b>x</b>**")).toBe("2 ** 3 and <strong>&lt;b&gt;x&lt;/b&gt;</strong>");
  });

  it("keeps plain text and code as before", () => {
    expect(html("plain")).toBe("plain");
    expect(renderMarkdown("- [x] **C1**: `ok`").outerHTML).toContain("<strong>C1</strong>: <code>ok</code>");
  });
});
