import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const pages = [
  "index.astro",
  "issues.astro",
  "sessions.astro",
  "usage.astro",
];

describe("kuhy-credit on all pages", () => {
  for (const page of pages) {
    it(`${page} contains <kuhy-credit> and imports the package`, () => {
      const content = fs.readFileSync(
        path.join(import.meta.dirname, "..", "pages", page),
        "utf8"
      );
      expect(content).toContain("<kuhy-credit></kuhy-credit>");
      expect(content).toContain('import "@kuhyx/kuhy-credit"');
    });
  }
});