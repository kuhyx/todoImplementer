import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(import.meta.dirname, "header.css"), "utf8");

describe("header banner width", () => {
  it("[T2001] a long path in a banner wraps instead of widening the page and the full-screen create dialog", () => {
    const usage = css.slice(css.indexOf(".usage-body {"));
    expect(usage.slice(0, usage.indexOf("}"))).toContain("min-width: 0");
    const banner = css.slice(css.indexOf(".banner,"));
    expect(banner.slice(0, banner.indexOf("}"))).toContain("overflow-wrap: anywhere");
  });
});
