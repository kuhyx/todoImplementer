/** Mock data for the umbrella tracking view: the shared contract fixture, rebased onto the mock's clock. */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import type { TaskCard } from "@/lib/schemas-common";

import { makeCards, NOW } from "#fixtures/fixtures";

export const TRACK_ID = "2d0704cd-0";
const RAW = JSON.parse(readFileSync(join(import.meta.dirname, "..", "..", "tests", "fixtures", "track.json"), "utf8")) as {
  at: number;
  counts: NonNullable<TaskCard["umbrella"]>;
  title: string;
};
const TIMES = new Set(["at", "ended", "last", "started", "ts", "until"]);

function rebase(value: unknown, delta: number, key = ""): unknown {
  if (typeof value === "number") return TIMES.has(key) ? value + delta : value;
  if (Array.isArray(value)) return value.map((item) => rebase(item, delta, key));
  return value !== null && typeof value === "object" ? Object.fromEntries(Object.entries(value).map(([k, v]) => [k, rebase(v, delta, k)])) : value;
}

/** The fixture with every instant moved so that `at` is NOW (the mock server then shifts NOW to the real clock). */
export function trackBody(): unknown {
  return rebase(RAW, NOW - RAW.at);
}

/** The board card the track link sits on: a working card with the fixture's counts. */
export function umbrellaCard(): TaskCard {
  const base = makeCards().find((card) => card.status === "working");
  if (base === undefined) throw new Error("no working fixture card");
  return { ...base, id: TRACK_ID, title: RAW.title, umbrella: RAW.counts };
}

export function workerLog(child: string): string {
  return [`worker log of ${child}`, "Reading the repo...", "Editing src/ui/label.ts", "Done: 3 files changed", ""].join("\n");
}
