/**
 * Renders the launcher icons from public/favicon.svg (the shared family: charcoal field + accent glyph) with rsvg-convert.
 * Run: `pnpm icons`. Output is committed (public/icons/*.png), so the build needs no rasteriser.
 *
 * icon-192 / icon-512 (purpose "any"): the favicon as is, rounded field.
 * icon-maskable-512: full-bleed square (Android crops its own shape) with the glyph shrunk so its farthest stroke point
 * stays inside the 80 % safe circle (radius 0.4 of the size); the favicon's glyph reaches 0.375, shrunk it reaches 0.32.
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const PUBLIC = join(import.meta.dirname, "..", "public");
const OUT = join(PUBLIC, "icons");
const SHRINK = 0.85;
const RSVG = "/usr/bin/rsvg-convert";

/** The favicon's field colour and glyph, read from its markup so the icons can never drift from it. */
function parts(favicon: string): { field: string; glyph: string } {
  const field = /<rect[^>]*fill="(#[0-9a-f]{6})"/u.exec(favicon)?.[1];
  const glyph = /<path[^>]*\/>/u.exec(favicon)?.[0];
  if (field === undefined || glyph === undefined) throw new Error("favicon.svg: expected one filled rect and one path");
  return { field, glyph };
}

const favicon = readFileSync(join(PUBLIC, "favicon.svg"), "utf8");
const { field, glyph } = parts(favicon);
const maskable =
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" fill="${field}"/>` +
  `<g transform="translate(16 16) scale(${String(SHRINK)}) translate(-16 -16)">${glyph}</g></svg>`;

function render(svg: string, size: number, file: string): void {
  const png = execFileSync(RSVG, ["-w", String(size), "-h", String(size), "-f", "png"], { input: svg, maxBuffer: 1 << 24 });
  writeFileSync(join(OUT, file), png);
  console.log(`${file} ${String(size)}x${String(size)} ${String(png.length)} bytes`);
}

mkdirSync(OUT, { recursive: true });
render(favicon, 192, "icon-192.png");
render(favicon, 512, "icon-512.png");
render(maskable, 512, "icon-maskable-512.png");
