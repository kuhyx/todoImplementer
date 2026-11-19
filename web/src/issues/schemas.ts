/**
 * One line of free-issues.jsonl (server/todoimpl/umbrella/issues.py), parsed in the page. The manager writes these by
 * hand, so the parse is tolerant: optional fields fall back to their defaults and a line that is not an issue object
 * is kept as a raw row, never dropped.
 */
import { z } from "zod";

export const issueLine = z.object({
  action: z.string().catch(""),
  child: z.string(),
  fixed: z.boolean().catch(false),
  /** null (no model) and any other non-string both read as "". */
  model: z.string().catch(""),
  phase: z.string(),
  symptom: z.string(),
  ts: z.number(),
});

export type IssueState = "fixed" | "open" | "raw";

export interface Issue {
  action: string;
  child: string;
  /** Line number in the log, 1-based: the stable row id and the tie-break of the newest-first order. */
  line: number;
  model: string;
  phase: string;
  /** The line as written; only shown for raw rows. */
  raw: string;
  state: IssueState;
  symptom: string;
  /** Unix seconds; null for a raw row. */
  ts: null | number;
}

function rawIssue(line: number, raw: string): Issue {
  return { action: "", child: "", line, model: "", phase: "", raw, state: "raw", symptom: raw, ts: null };
}

function parseLine(line: number, raw: string): Issue {
  let found: unknown;
  try {
    found = JSON.parse(raw);
  } catch {
    return rawIssue(line, raw);
  }
  const parsed = issueLine.safeParse(found);
  if (!parsed.success) return rawIssue(line, raw);
  const { action, child, fixed, model, phase, symptom, ts } = parsed.data;
  return { action, child, line, model, phase, raw, state: fixed ? "fixed" : "open", symptom, ts };
}

/** Every non-blank line of the log, in file order. */
export function parseLog(text: string): Issue[] {
  return text.split("\n").flatMap((raw, index) => (raw.trim() === "" ? [] : [parseLine(index + 1, raw)]));
}
