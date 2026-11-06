/** Pure model of the question flow: which ask a task has, the effective answer, the first open question, swipes and the payload. */
import type { TaskDetail } from "@/lib/schemas";
import type { Question } from "@/lib/schemas-common";

export type Ask = { kind: "free"; text: string } | { kind: "spec"; questions: Question[] };

/** A horizontal move this long (and mostly horizontal) counts as a swipe. */
export const SWIPE_PX = 80;

/** Structured spec questions, or a plain "Q:" rest whose only text is the card's needs text. */
export function askOf(detail: TaskDetail): Ask | null {
  if (detail.questions.length > 0) return { kind: "spec", questions: detail.questions };
  const { needs } = detail.card;
  return needs?.kind === "claude_question" ? { kind: "free", text: needs.text } : null;
}

/** A card that needs spec answers shows only the question flow until "Details" is opened. */
export const isOnlyAsk = (detail: TaskDetail): boolean => detail.card.needs?.kind === "spec_questions" && detail.questions.length > 0;

/** Draft first, then the saved answer, then Claude's recommendation. */
export const effective = (question: Question, drafts: Readonly<Record<string, string>>): string =>
  drafts[question.id] ?? question.answer ?? question.recommendation;

/** The first question with no saved answer; the flow starts there (0 when all are answered). */
export const firstOpen = (questions: readonly Question[]): number =>
  Math.max(0, questions.findIndex((question) => (question.answer ?? "") === ""));

/** The next question after `step` with no saved answer, or -1 when none is left (the flow then sends). */
export const nextOpen = (questions: readonly Question[], step: number): number =>
  questions.findIndex((question, index) => index > step && (question.answer ?? "") === "");

/** Why OK cannot send yet; the answers stay on this device and go out by themselves once it can. */
export const waitingNote = (reason: string): string => {
  const why = reason === "" ? "" : `Cannot send yet: ${reason}. `;
  return `${why}Your answers are kept here and sent as soon as Claude can take them.`;
};

export const NOT_WAITING = "These questions are not waiting for an answer.";

export function answersOf(questions: readonly Question[], drafts: Readonly<Record<string, string>>): Record<string, string> {
  const answers: Record<string, string> = {};
  for (const question of questions) {
    const value = effective(question, drafts).trim();
    if (value !== "") answers[question.id] = value;
  }
  return answers;
}

/** Swipe right accepts ("next"), swipe left goes "back"; anything short or mostly vertical is a scroll. */
export function swipeOf(dx: number, dy: number): "back" | "next" | null {
  if (Math.abs(dx) < SWIPE_PX || Math.abs(dx) < 2 * Math.abs(dy)) return null;
  return dx > 0 ? "next" : "back";
}

export const progressLabel = (step: number, total: number): string => `${String(step + 1)} / ${String(total)}`;

export const sendingLabel = (count: number): string => `Sending ${String(count)} answer${count === 1 ? "" : "s"}…`;
