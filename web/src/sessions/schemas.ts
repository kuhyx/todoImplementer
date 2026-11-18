/** Zod mirror of contracts/sessions.schema.json: the shape is checked once, at the fetch boundary. */
import { z } from "zod";

export const STATUSES = ["needs_action", "question", "untagged", "running", "done", "continuing"] as const;
export const MARKS = ["manual", "tag", "open"] as const;

export const status = z.enum(STATUSES);
export const sessionId = z.string().regex(/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/v);

export const session = z.strictObject({
  cwd: z.string(),
  done: z.boolean(),
  group: z.union([z.literal(0), z.literal(1), z.literal(2), z.literal(3), z.literal(4)]),
  id: sessionId,
  last_assistant: z.string(),
  last_ts: z.string().nullable(),
  last_user: z.string(),
  manual_mark: z.literal("done").nullable(),
  mark: z.enum(MARKS),
  movable: z.boolean(),
  move_reason: z.string().nullable(),
  project: z.string(),
  resume_command: z.string(),
  status,
  title: z.string(),
});

export const sessionList = z.strictObject({
  scan_ms: z.number().min(0),
  scanned: z.number().int().min(0),
  sessions: z.array(session),
});

/** The answer to every mutation, a refusal included (HTTP 200); `refused` is the guard working, not a crash. */
export const mutationResult = z.strictObject({
  argv: z.array(z.string()),
  ok: z.boolean(),
  refused: z.boolean(),
  stderr: z.string(),
  stdout: z.string(),
  summary: z.string(),
});

export type Session = z.infer<typeof session>;
export type SessionList = z.infer<typeof sessionList>;
export type MutationResult = z.infer<typeof mutationResult>;
export type Status = z.infer<typeof status>;
export type Mark = (typeof MARKS)[number];
