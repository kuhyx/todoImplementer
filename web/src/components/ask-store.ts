/** Drafts, the step and a queued send per card in localStorage, so a closed drawer, a reload or a reboot keeps the progress. */
import { z } from "zod";

import type { Question } from "@/lib/schemas-common";

const stored = z.object({
  drafts: z.record(z.string(), z.string()),
  queued: z.boolean().default(false),
  step: z.number().int().min(0),
});
export type AskState = z.infer<typeof stored>;

export const blankState = (step: number): AskState => ({ drafts: {}, queued: false, step });

export const storeKey = (cardId: string, questions: readonly Question[]): string =>
  `todoimpl.ask.${cardId}.${questions.map((question) => question.id).join(",")}`;

export function loadState(key: string): AskState | null {
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw === null ? null : stored.safeParse(JSON.parse(raw));
    return parsed?.success === true ? parsed.data : null;
  } catch {
    return null;
  }
}

export function saveState(key: string, state: AskState): void {
  try {
    localStorage.setItem(key, JSON.stringify(state));
  } catch {
    // Storage is blocked or full: the draft then lives in memory until the drawer closes.
  }
}

export function dropState(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // Nothing was stored, so there is nothing to drop.
  }
}
