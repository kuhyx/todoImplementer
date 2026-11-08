/** Pure model of the question flow: which ask a task has, the effective answer, the first open question, swipes and the payload. */
import type { TaskDetail } from "@/lib/schemas";
import type { Question } from "@/lib/schemas-common";

export type Ask = { kind: "free"; questions: Question[]; text: string } | { kind: "spec"; questions: Question[] };

/** A horizontal move this long (and mostly horizontal) counts as a swipe. */
export const SWIPE_PX = 80;

/** An open Claude question (its parsed cards, else the card's needs text as one question), else structured spec questions. */
export function askOf(detail: TaskDetail): Ask | null {
  // An open Claude question wins over spec questions answered earlier in the run (T1816).
  const { needs } = detail.card;
  if (needs?.kind === "claude_question") {
    return { kind: "free", questions: detail.asks.length > 0 ? detail.asks : [freeQuestion(needs.text)], text: needs.text };
  }
  return detail.questions.length > 0 ? { kind: "spec", questions: detail.questions } : null;
}

/** A plain Claude question goes through the same one-question view: one synthetic question whose answer is sent as a message. */
export const freeQuestion = (text: string): Question => ({ answer: null, body: text, id: "Q1", recommendation: "", title: "Claude asks" });

/** The questions the flow walks: the structured ones, or the one synthetic question of a plain Claude question. */
export const questionsOf = (ask: Ask): Question[] => ask.questions;

/** The one message a Claude question's answers go out as: the bare answer for one question, one labelled paragraph each for several. */
export function replyOf(questions: readonly Question[], answers: Readonly<Record<string, string>>): string {
  return questions.length === 1 ? Object.values(answers).join("") : questions
    .filter((question) => answers[question.id] !== undefined)
    .map((question) => `${question.id} (${question.title}): ${answers[question.id] ?? ""}`)
    .join("\n\n");
}

/** A card that waits for an answer shows only the question flow until "Details" is opened. */
export const isOnlyAsk = (detail: TaskDetail): boolean =>
  askOf(detail)?.kind === "free" || (detail.card.needs?.kind === "spec_questions" && detail.questions.length > 0);

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

export const sendingLabel = (count: number): string => `Sending ${String(count)} answer${count === 1 ? "" : "s"}…`;
