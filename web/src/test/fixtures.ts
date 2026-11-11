/**
 * Real-shaped fixtures (R10): 38 notes over 29 repos, 7 without a repo, mixed
 * priorities, a null `updated`, long and unbroken titles, markup characters in
 * titles. NOW is pinned so relative times are stable.
 */
import type { Board } from "@/lib/schemas";
import type { TaskCard } from "@/lib/schemas-common";

import { makeCredits } from "./fixture-credits.ts";
import { preset } from "./fixture-presets.ts";

export const NOW = 1_793_000_000;
const LONG =
  "Rework the nightly backup verification so that a partially written archive is detected before the retention sweep deletes the previous good one and the report names the exact file";
const UNBROKEN = "server/todoimpl/runner/extremely_long_module_name_without_any_break_opportunity_at_all_in_it.py";

type Row = readonly [
  repo: null | string,
  title: string,
  status: TaskCard["status"],
  priority: string,
  cost: number,
  ago: null | number,
];

const ROWS: readonly Row[] = [
  ["todo", "Sync conflict dialog shows both versions", "backlog", "high", 0, 86_400],
  ["control-panel", "Show unit state on every card", "backlog", "medium", 0, 7200],
  ["personal-website", "Add print stylesheet for the CV", "backlog", "low", 0, 300_000],
  ["screen-locker", LONG, "backlog", "high", 0, 4000],
  ["steam-backlog-enforcer", "Pause enforcement during sleep window", "backlog", "medium", 0, null],
  ["wake-alarm", UNBROKEN, "backlog", "urgent", 0, 900],
  ["dufs-cloud", "Upload progress per file", "backlog", "low", 0, 172_800],
  ["workout-app", "Log RPE per set", "backlog", "medium", 0, 50_000],
  ["diet-guard-app", "Barcode scan falls back to manual entry", "backlog", "high", 0, 1200],
  ["kcd2-dice-solver", "Odds table sortable by column", "backlog", "low", 0, 9_000_000],
  ["signal-bot", "Reply to !help in groups too", "backlog", "medium", 0, 3000],
  ["utils", "Fuzzy search ranks prefix matches first", "backlog", "medium", 0, 1000],
  ["wiki-kb", "Resume interrupted crawl", "backlog", "low", 0, 600],
  ["lyrics-heat", "Per-decade chart labels", "backlog", "low", 0, 60],
  [null, "Call the dentist about the crown", "yours", "high", 0, 100_000],
  [null, "Renew passport before the trip", "yours", "urgent", 0, 20_000],
  [null, 'Decide on the standing desk <b>height</b> & "tilt"', "yours", "medium", 0, 5000],
  [null, "Read the thesis chapter 3 comments", "yours", "medium", 0, 7000],
  [null, "Cancel the unused cloud subscription", "yours", "low", 0, 400_000],
  [null, "Sort the cable drawer", "yours", "low", 0, 800_000],
  [null, "Buy a replacement NVMe", "yours", "medium", 0, 33_000],
  ["tutor", "Hint ladder never repeats a tier", "cancelled", "medium", 0.42, 30_000],
  ["gatelock", "Escape hatch needs keyboard path", "working", "high", 3.18, 40],
  ["praca-magisterska", "Chapter 4 figure refresh", "working", "medium", 1.07, 12],
  ["music-theory", "Render the loop bed at 44.1 kHz", "working", "low", 0.66, 5],
  ["teatr-pw", "Seat map keyboard navigation", "queued", "medium", 0, 20],
  ["awesome-mcp-explorer", "Filter by transport", "paused_limit", "medium", 2.2, 3000],
  ["ts-config", "Fast subset reports unused imports", "needs_you", "high", 0.9, 700],
  ["design-system", "Palette check covers Tkinter", "needs_you", "medium", 0.35, 2000],
  ["sleep-tracker", "Store naps as a separate series", "needs_you", "low", 0.12, 1500],
  ["foss-audit", "Licence column links the licence text", "needs_you", "medium", 1.4, 90],
  ["todo", "Widget shows next three tasks", "ready_to_ship", "high", 4.51, 600],
  ["utils", "Dependency freshness explains the carve-out", "ready_to_ship", "medium", 2.9, 1800],
  ["flutter-web-drive", "Tap by semantics label prefix", "ready_to_ship", "low", 1.77, 4000],
  ["vmbox", "Snapshot before pacman test", "done", "medium", 2.1, 90_000],
  ["linux-configuration", "Timer unit for night lockdown", "done", "high", 5, 200_000],
  ["agent-ready", "llms.txt generated from routes", "done", "low", 0.88, 360_000],
  ["ts-config", "Boundaries preset documents elements", "done", "low", 1.2, 500_000],
];

const NO_TIER = { cheap: false, escalated: false, free: false };
/** Cheap-tier badge combinations on a few cards, so the viewport checks see icons next to long titles. */
const TIERS: Record<string, TaskCard["tier"]> = {
  "Chapter 4 figure refresh": { cheap: true, escalated: false, free: true },
  "Palette check covers Tkinter": { cheap: true, escalated: true, free: false },
  "Render the loop bed at 44.1 kHz": { cheap: true, escalated: false, free: false },
};

function idFor(index: number): string {
  return `${(index + 1).toString(16).padStart(2, "0")}a1b2c3-0`;
}

export function makeCards(): TaskCard[] {
  return ROWS.map(([repository, title, status, priority, cost, ago], index) => {
    return {
      ...preset(status, repository !== null),
      assignee: repository === null ? "human" : "claude",
      auto: null,
      auto_start: null,
      cost_usd: cost,
      id: idFor(index),
      partial: null,
      priority,
      repo: repository,
      resumes_at: status === "paused_limit" ? NOW + 3 * 3600 : null,
      route: null,
      tier: TIERS[title] ?? NO_TIER,
      title,
      updated: ago === null ? null : NOW - ago,
    };
  });
}

const LABELS = {
  backlog: "Backlog",
  done: "Done",
  needs_you: "Needs you",
  ready: "Ready to ship",
  running: "Running",
};

export function makeBoard(cards: TaskCard[] = makeCards()): Board {
  const ids = ["backlog", "running", "needs_you", "ready", "done"] as const;
  const names = cards.map((card) => card.repo).filter((repo) => repo !== null);
  const repos = [...new Set(names)].toSorted((a, b) => a.localeCompare(b));
  return {
    auto_close: false,
    build: "abc1234",
    columns: ids.map((id) => ({ count: cards.filter((card) => card.column === id).length, id, label: LABELS[id] })),
    generated_at: NOW,
    limit: { active: false, credits: makeCredits(), until: null },
    repos,
    slots: { used: cards.filter((card) => card.status === "working").length },
    tasks: cards,
  };
}
