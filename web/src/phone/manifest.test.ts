import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { z } from "zod";

const PUBLIC = join(import.meta.dirname, "..", "..", "public");
const PAGES = join(import.meta.dirname, "..", "pages");
const manifest = z
  .looseObject({
    background_color: z.string().regex(/^#[0-9a-f]{6}$/u),
    display: z.literal("standalone"),
    icons: z.array(z.strictObject({ purpose: z.enum(["any", "maskable"]), sizes: z.string(), src: z.string(), type: z.literal("image/png") })),
    name: z.literal("todoImplementer"),
    scope: z.literal("/"),
    short_name: z.string().min(1).max(12),
    start_url: z.literal("/"),
    theme_color: z.string().regex(/^#[0-9a-f]{6}$/u),
  })
  .parse(JSON.parse(readFileSync(join(PUBLIC, "manifest.webmanifest"), "utf8")));

/** PNG: 8-byte signature, then the IHDR chunk with width and height as big-endian u32 at bytes 16 and 20. */
function pngSize(path: string): { height: number; width: number } {
  const bytes = readFileSync(path);
  expect([bytes.readUInt32BE(0), bytes.readUInt32BE(4)]).toEqual([0x89_50_4E_47, 0x0D_0A_1A_0A]);
  expect(bytes.subarray(12, 16).toString("ascii")).toBe("IHDR");
  return { height: bytes.readUInt32BE(20), width: bytes.readUInt32BE(16) };
}

describe("web app manifest", () => {
  it("uses the design system's charcoal for background and theme", () => {
    expect(manifest.background_color).toBe("#211d1b");
    expect(manifest.theme_color).toBe("#211d1b");
  });

  it("declares 192 and 512 icons for purpose any and a 512 maskable one", () => {
    const keys = manifest.icons.map((icon) => `${icon.sizes}/${icon.purpose}`).toSorted((a, b) => a.localeCompare(b));
    expect(keys).toEqual(["192x192/any", "512x512/any", "512x512/maskable"]);
  });

  it.each(["192x192/any", "512x512/any", "512x512/maskable"])("icon %s exists at its declared size", (key) => {
    const icon = manifest.icons.find((candidate) => `${candidate.sizes}/${candidate.purpose}` === key);
    expect(icon).toBeDefined();
    const size = Number(icon?.sizes.split("x", 1)[0]);
    expect(pngSize(join(PUBLIC, icon?.src ?? ""))).toEqual({ height: size, width: size });
  });
});

describe("page heads", () => {
  it.each(["index", "usage", "sessions"])("%s links the manifest, theme colour and apple icon", (page) => {
    const source = readFileSync(join(PAGES, `${page}.astro`), "utf8");
    expect(source).toContain('<link rel="manifest" href="/manifest.webmanifest" />');
    expect(source).toContain('<meta name="theme-color" content="#211d1b" />');
    expect(source).toContain('<link rel="apple-touch-icon" href="/icons/icon-192.png" />');
    expect(source).not.toContain("serviceWorker");
  });
});
