/** Task-detail, usage and live-event fixtures built on the board fixtures. */
import type { LiveEvent, TaskDetail, Usage } from "@/lib/schemas";
import type { TaskCard } from "@/lib/schemas-common";

import { makeCredits } from "./fixture-credits.ts";
import { makeFree } from "./fixture-free.ts";
import { NOW } from "./fixtures.ts";

const PLAN = [
  "# Plan",
  "",
  "## Acceptance criteria",
  "- [ ] `pnpm test` passes with 100 % coverage",
  "- [ ] The page shows the new state within 100 ms",
  "",
  "1. Write the failing test",
  "2. Implement it",
  "",
  "```",
  "make check",
  "```",
  "",
].join("\n");

const PATCH = [
  "diff --git a/src/a.ts b/src/a.ts",
  "index 111..222 100644",
  "--- a/src/a.ts",
  "+++ b/src/a.ts",
  "@@ -1,3 +1,4 @@",
  " export const a = 1;",
  "-export const b = 2;",
  "+export const b = 3;",
  "+export const c = 4;",
  "",
].join("\n");

export function makeDetail(card: TaskCard): TaskDetail {
  const isNeedsSpec = card.needs?.kind === "spec_questions";
  const isWorked = card.column === "done" || card.status === "shipping" || card.status === "working";
  return {
    ask_items: [],
    asks: [],
    body: `${card.title}\n\nDone when the behaviour is visible in the app.`,
    branch: isWorked ? `todoimpl/${card.id}` : null,
    card,
    checks: isWorked
      ? {
          log: "logs/checks-1.log",
          passed: false,
          ran_at: NOW - 600,
          results: [
            { command: "make check", exit: 0, tail: "42 passed in 3.1 s\nruff: all checks passed" },
            { command: "pre-commit run --all-files", exit: 1, tail: "mypy: 1 error in src/a.ts" },
          ],
        }
      : null,
    diff: isWorked ? { files: [{ added: 2, path: "src/a.ts", removed: 1 }], patch: PATCH, truncated: false } : null,
    done_check: isWorked ? "make check" : null,
    error: null,
    lesson:
      card.status === "shipping"
        ? { evidence: "kuhy rejected the first push", id: "l1", mistake: "Skipped the red test", rule: "Show the red run first.", skill: "build-web-ui", state: "drafted" }
        : null,
    live_check: isWorked
      ? { report_md: "## Live check\n- Opened the page at 390x844: **board shown**\n- `Ship` button visible", shots: ["live/board.png", "live/drawer.png"] }
      : null,
    plan_md: isWorked || isNeedsSpec ? PLAN : null,
    questions: isNeedsSpec
      ? [
          { answer: null, body: "Which storage should the setting use?", id: "Q1", recommendation: "localStorage", title: "Storage" },
          { answer: "Yes", body: "Should it sync?", id: "Q2", recommendation: "No", title: "Sync" },
        ]
      : [],
    resume_command: isWorked ? `cd /tmp/wt/${card.id} && claude --resume 0b1c2d3e` : null,
    self_check: isWorked
      ? [
          { criterion: "pnpm test passes", done: true, note: "42 passed" },
          { criterion: "Page updates within 100 ms", done: false },
        ]
      : [],
    skills_loaded: isWorked ? ["build-web-ui", "safe-design-rules"] : [],
    stages: isWorked
      ? [
          { ended: NOW - 900, stage: "plan", started: NOW - 1800 },
          { ended: null, stage: "implement", started: NOW - 900 },
        ]
      : [],
    worktree: isWorked ? `/tmp/wt/${card.id}` : null,
  };
}

export function makeAutonomy(): Usage["autonomy"] {
  return {
    backfilled: 3,
    cards: 6,
    criteria_failed: { direction: "down", target: 0, value: 3, weekly: [{ value: 1, week: "2026-W44" }, { value: 2, week: "2026-W45" }] },
    done_unassisted: {
      count: 2,
      direction: "up",
      finished: 5,
      target: 100,
      value: 40,
      weekly: [{ count: 1, finished: 3, value: 33.3, week: "2026-W44" }, { count: 1, finished: 2, value: 50, week: "2026-W45" }],
    },
    permission_asks: { direction: "down", target: 0, value: 0, weekly: [] },
    questions_asked: { direction: "down", target: 0, value: 12, weekly: [{ value: 12, week: "2026-W45" }] },
  };
}

export function makeUsage(): Usage {
  return {
    autonomy: makeAutonomy(),
    cost: { per_task: [{ cost_usd: 3.18, id: "17a1b2c3-0", title: "Escape hatch" }], today_usd: 12.37, total_usd: 80.5 },
    five_hour: { resets_at: NOW + 8100, status: "allowed", utilization: 0.42 },
    free: makeFree(),
    generated_at: NOW,
    limit: { active: false, credits: makeCredits(), until: null, weekly_allowance: null, weekly_hold: "none", weekly_used: null },
    overage: { status: "rejected", using: false },
    seven_day: { resets_at: NOW + 3 * 86_400, status: "allowed_warning", utilization: 0.77 },
  };
}

export const LIVE_EVENTS: LiveEvent[] = [
  { actions: [], column: "running", current: "implementing: step 2 of 4", needs: null, stage: "implement", status: "working", type: "stage" },
  { at: NOW - 30, kind: "text", seq: 1, text: "Reading the plan", tool: null, type: "activity" },
  { at: NOW - 20, kind: "tool", seq: 2, text: "pnpm test", tool: "Bash", type: "activity" },
  { at: NOW - 10, kind: "error", seq: 3, text: "1 failed", tool: null, type: "activity" },
  { cost_usd: 3.2, type: "cost" },
];
