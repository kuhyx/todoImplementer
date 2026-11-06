/**
 * Real-shaped spec questions (R10): ~250-character bodies, ~150-character recommendations, a 5-line title.
 * They back the dev mock's ask cards, the viewport `questions` step and the unit tests.
 */
import type { TaskDetail } from "@/lib/schemas";
import type { Question, TaskCard } from "@/lib/schemas-common";

import { makeDetail } from "./fixture-detail.ts";
import { makeCards } from "./fixtures.ts";

export const ASK_ID = "f1a1b2c3-0";
export const ASK9_ID = "f2a1b2c3-0";
export const FREE_ID = "f3a1b2c3-0";
export const ASK_IDS = [ASK_ID, ASK9_ID, FREE_ID];

const TITLE =
  "Make the nightly backup verification catch a partially written archive before the retention sweep deletes the previous good one, name the exact file in the report, and keep the run under the five-minute budget on the slowest disk";
const BODY = [
  "The verifier currently trusts the archive size recorded in the manifest, which is written before the last chunk is flushed. A crash in between leaves a short file with a matching size, so the check passes on a broken archive.",
  "Today the report prints one line per repository and no file name. When two archives fail on the same night kuhy cannot tell which one to restore first, and the retention sweep has already pruned the older copy by then.",
  "The sweep runs from a systemd timer ten minutes after the backup. If verification is moved in front of it the timer ordering changes, and a slow disk could push the sweep past the point where the previous archive is still safe to delete.",
  "A checksum pass over every archive doubles the nightly I/O on the spinning disk. A sampled check reads far less but can miss a corrupt chunk in the middle, so the choice trades certainty for the five-minute budget.",
  "Notifications go to the existing desktop notifier only. A failed verification at 03:10 is seen the next morning at the earliest, after the sweep has run, so the alert may arrive too late to save the previous archive.",
];
const REC = [
  "Verify the final chunk checksum and compare it to the manifest after the flush; fail the run if either differs, and leave the previous archive untouched.",
  "Print one line per failed file with its full path and size, sorted by age, so the oldest damaged archive is restored first and nothing is guessed.",
  "Run the verifier as a Before= dependency of the sweep unit so the sweep never starts on a failed night; keep the timer time unchanged for now.",
  "Checksum every archive but read at most the newest two per repository; this stays under the budget on the slow disk and covers the copies that matter.",
  "Send a critical notification and write a marker file that makes the sweep skip pruning until kuhy removes it by hand; no new notifier is added.",
];
const NAMES = ["Verification", "Report", "Ordering", "Coverage", "Alerting", "Retention", "Rollback", "Logging", "Schedule"];

export function askQuestions(count = 5): Question[] {
  return Array.from({ length: count }, (_, index) => {
    return {
      answer: null,
      body: BODY[index % BODY.length] ?? "",
      id: `Q${String(index + 1)}`,
      recommendation: REC[index % REC.length] ?? "",
      title: NAMES[index % NAMES.length] ?? "Question",
    };
  });
}

function needsCard(id: string, kind: "claude_question" | "spec_questions", text: string): TaskCard {
  const base = makeCards().find((card) => card.status === "needs_you");
  if (base === undefined) throw new Error("fixture has no needs_you card");
  const send = { enabled: true, id: "send" as const, label: "Send to Claude", reason: null };
  const actions = kind === "claude_question" ? [send, ...base.actions.filter((a) => a.id === "cancel")] : base.actions;
  return { ...base, actions, id, needs: { category: "questions", effort: 2, kind, text }, title: TITLE };
}

export function askDetail(id: string): TaskDetail {
  const count = id === ASK9_ID ? 9 : 5;
  const card = needsCard(id, "spec_questions", `${String(count)} open question(s) from Claude`);
  return {
    ...makeDetail(card),
    card: { ...card, actions: card.actions.map((a) => (a.id === "spec-answers" ? { ...a, label: "Send answers" } : a)) },
    questions: askQuestions(count),
  };
}

export function freeDetail(): TaskDetail {
  const card = needsCard(FREE_ID, "claude_question", "Claude asked a question: answer it with Send to Claude");
  return { ...makeDetail(card), questions: [] };
}

export const askCards = (): TaskCard[] => ASK_IDS.map((id) => (id === FREE_ID ? freeDetail() : askDetail(id)).card);
