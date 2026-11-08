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
  "Make the nightly backup verification catch a partially written archive before the retention sweep deletes the previous good one, name the exact file in the report, keep the run under the five-minute budget on the slowest disk, and make sure a failed night leaves the previous archive untouched until kuhy has looked at it";
const BODY = [
  "The verifier currently trusts the archive size recorded in the manifest, which is written before the last chunk is flushed. A crash in between leaves a short file with a matching size, so the check passes on a broken archive.",
  "Today the report prints one line per repository and no file name. When two archives fail on the same night kuhy cannot tell which one to restore first, and the retention sweep has already pruned the older copy by then.",
  "Should the sweep wait for verification?",
  [
    "A checksum pass over every archive doubles the nightly I/O on the spinning disk. A sampled check reads far less but can miss a corrupt chunk in the middle, so the choice trades certainty for the five-minute budget.",
    "The disk is a single spinning drive shared with the photo library, so a full pass competes with the thumbnail job that starts at the same minute. Measured on the slowest disk the full pass takes about eleven minutes.",
    "Reading only the newest two archives per repository takes under two minutes, but the older copies are then never verified until the day they are the only ones left, which is exactly when a silent failure hurts most.",
    "A middle path is to checksum the newest two every night and one older archive per night in rotation, so every copy is read at least once a fortnight. That keeps the budget but needs a small state file for the rotation.",
  ].join("\n\n"),
  "Notifications go to the existing desktop notifier only. A failed verification at 03:10 is seen the next morning at the earliest, after the sweep has run, so the alert may arrive too late to save the previous archive.",
];
const REC = [
  "Verify the final chunk checksum and compare it to the manifest after the flush; fail the run if either differs, and leave the previous archive untouched.",
  "Print one line per failed file with its full path and size, sorted by age, so the oldest damaged archive is restored first and nothing is guessed.",
  "Run the verifier as a Before= dependency of the sweep unit so the sweep never starts on a failed night; keep the timer time unchanged for now.",
  "Checksum every archive but read at most the newest two per repository; this stays under the budget on the slow disk and covers the copies that matter. " +
    "Add the rotation: one older archive per night, chosen by the oldest last-verified time kept in a small state file next to the manifest, so every copy is read at least once a fortnight. " +
    "If the state file is missing or unreadable, verify the newest two only and log that the rotation restarted; never fail the night because of the state file itself. " +
    "Report the rotation position in the same line as the file name so a reader sees at once how stale the oldest unverified copy is. " +
    "Keep the thumbnail job's start time unchanged and run the verifier at nice 19 with idle I/O priority so the two never fight for the disk.",
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

/** T1816: a Claude question asked mid-run, after every spec question was answered: the reply's cards arrive as `asks`. */
export function laterDetail(asks = 2): TaskDetail {
  const card = needsCard(FREE_ID, "claude_question", "allow request pacing so the cache repair can finish?");
  const answered = askQuestions(3).map((question) => ({ ...question, answer: question.recommendation }));
  return { ...makeDetail(card), asks: askQuestions(asks), questions: answered };
}
