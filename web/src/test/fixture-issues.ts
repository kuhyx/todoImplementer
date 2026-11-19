/** A free-issues.jsonl with the real log's shape: long symptoms, null and named models, fixed and open, a hand-written line. */
export const TASK = "2556952d-0";
/** 2026-11-20T08:00:00Z, the harness clock, in Unix seconds. */
export const NOW_S = 1_795_161_600;

const line = (ts: number, child: string, phase: string, model: null | string, isFixed: boolean, symptom: string, action = ""): string =>
  JSON.stringify({ action, child, fixed: isFixed, model, phase, symptom, ts });

export const LINES = [
  line(NOW_S - 7200, "kuhyx/CV", "start", null, true, "child marked free: no; no free worker allowed", "manager did the edit locally; pre-commit all-files green"),
  line(NOW_S - 5400, "kuhyx/explorer", "prompt", "free-best", false, "Worker removed the CI workflow but left pre-commit red: node 26.13.0->26.13.1, pnpm 12.18.0->12.21.0 and 8 more pins behind latest stable", "Rerun worker with task-b.md listing every exact pin bump"),
  line(NOW_S - 3600, "kuhyx/explorer", "output", "free-best", true, "worker-2-b.log: lost (the worker died without an exit record)", "ran pnpm install, pnpm test (434 passed) myself and committed"),
  "manager note: gateway flapped twice, see worker-3.log",
  line(NOW_S - 600, "kuhyx/panel", "prompt", "free-fast", false, "Worker deleted dependency-freshness.yml but missed the ci.yml gate job"),
  JSON.stringify({ child: "kuhyx/panel", phase: "output", symptom: "no action or fixed field written", ts: NOW_S - 30 }),
];

export const LOG = `${LINES.join("\n")}\n\n`;
