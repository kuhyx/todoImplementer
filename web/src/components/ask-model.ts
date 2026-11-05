/** Pure model of the question UI: which ask a task has, the layout for a width, page fitting, the pager and the answers payload. */
import type { TaskDetail } from "@/lib/schemas";
import type { Question } from "@/lib/schemas-common";

export type Ask = { kind: "free"; text: string } | { kind: "spec"; questions: Question[] };
export interface Layout {
  cols: number;
  mode: "grid" | "step";
}
export interface Pager {
  back: readonly number[];
  start: number;
}

const STEP_BELOW = 480;
const COL_MIN = 360;
const COLS_MAX = 3;
/** Sub-pixel tolerance: the rect of a card that just fits can end a fraction past the area. */
const TOLERANCE = 0.5;

/** Structured spec questions, or a plain "Q:" rest whose only text is the card's needs text. */
export function askOf(detail: TaskDetail): Ask | null {
  if (detail.questions.length > 0) return { kind: "spec", questions: detail.questions };
  const { needs } = detail.card;
  return needs?.kind === "claude_question" ? { kind: "free", text: needs.text } : null;
}

export function layoutFor(width: number): Layout {
  return width < STEP_BELOW ? { cols: 1, mode: "step" } : { cols: Math.min(COLS_MAX, Math.max(1, Math.floor(width / COL_MIN))), mode: "grid" };
}

/** How many leading cards end inside the area; one at least, so a page is never empty. */
export function fitCount(bottoms: readonly number[], limit: number): number {
  if (bottoms.length === 0) return 0;
  const fits = bottoms.findIndex((bottom) => bottom > limit + TOLERANCE);
  return Math.max(1, fits === -1 ? bottoms.length : fits);
}

export const firstPage: Pager = { back: [], start: 0 };

export function nextPage(pager: Pager, count: number, total: number): Pager {
  return pager.start + count >= total ? pager : { back: [...pager.back, pager.start], start: pager.start + count };
}

export function previousPage(pager: Pager): Pager {
  const start = pager.back.at(-1);
  return start === undefined ? pager : { back: pager.back.slice(0, -1), start };
}

export const clampPager = (pager: Pager, total: number): Pager => (pager.start < total ? pager : firstPage);

export const isLast = (start: number, count: number, total: number): boolean => start + count >= total;

export function pageLabel(mode: Layout["mode"], start: number, count: number, total: number): string {
  if (start === 0 && isLast(start, count, total)) return "";
  if (mode === "step") return `${String(start + 1)} / ${String(total)}`;
  return count === 1 ? `${String(start + 1)} of ${String(total)}` : `${String(start + 1)}–${String(start + count)} of ${String(total)}`;
}

export const effective = (question: Question, edits: ReadonlyMap<string, string>): string =>
  edits.get(question.id) ?? question.answer ?? question.recommendation;

export function answersOf(questions: readonly Question[], edits: ReadonlyMap<string, string>): Record<string, string> {
  const answers: Record<string, string> = {};
  for (const question of questions) {
    const value = effective(question, edits).trim();
    if (value !== "") answers[question.id] = value;
  }
  return answers;
}
