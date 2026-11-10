/** The contract's sample tracking view (tests/fixtures/track.json, shared with the Python tests), parsed through Zod. */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { track, type Track } from "@/lib/schemas-track";

export const TRACK_ID = "2d0704cd-0";
const FILE = join(import.meta.dirname, "..", "..", "..", "tests", "fixtures", "track.json");

export function rawTrack(): Record<string, unknown> {
  return JSON.parse(readFileSync(FILE, "utf8")) as Record<string, unknown>;
}

/** A fresh deep copy each call; `patch` overrides top-level fields. */
export function makeTrack(patch: Partial<Track> = {}): Track {
  return { ...track.parse(rawTrack()), ...patch };
}
