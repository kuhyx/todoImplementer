/** Mock-server parts for the phone work: the pairing endpoint, the usage and sessions pages' data, MIME types. */
import { randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { sessionList } from "#fixtures/fixture-sessions";

const USAGE_FIXTURES = join(import.meta.dirname, "..", "src", "usage", "fixtures");
const PAIR_TTL_S = Number(process.env.MOCK_PAIR_TTL ?? 300);

export const PHONE_TYPES: Record<string, string> = { ".png": "image/png", ".webmanifest": "application/manifest+json" };

/** POST /api/pair answer: a one-time link valid for `MOCK_PAIR_TTL` seconds (default 300). */
export function pairBody(): unknown {
  return {
    expires_at: Math.floor(Date.now() / 1000) + PAIR_TTL_S,
    url: `https://agents.kuhy.duckdns.org/pair?c=${randomBytes(18).toString("base64url")}`,
  };
}

/** Pages are served from `dist/<page>/index.html`; the CSRF meta gets the local marker next to it, as the real server does for the PC. */
export const stampLocal = (html: string): string => html.replace('<meta name="todoimpl-csrf"', '<meta name="todoimpl-local" content="1" /><meta name="todoimpl-csrf"');

/** The fixture file behind a /api/tokens* path (panel/<name>, session/<id>, items, context-file, or the index). */
function usageFile(path: string): string {
  const [kind, name = ""] = path.split("/").slice(3);
  if (kind === undefined) return "index";
  if (kind === "session") return "session";
  return kind === "panel" ? name : kind;
}

/** The usage page's /api/tokens* data: each path maps to a captured fixture file; null when there is none. */
export async function usageFixture(path: string): Promise<unknown> {
  try {
    return JSON.parse(await readFile(join(USAGE_FIXTURES, `${usageFile(path)}.json`), "utf8"));
  } catch {
    return null;
  }
}

export const sessionsBody = (): unknown => sessionList();
