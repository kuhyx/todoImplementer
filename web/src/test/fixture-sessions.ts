/** Real-shaped /api/sessions payloads: the server's order (urgency group, newest first), a hand mark, a null time, a long reply. */
import type { MutationResult, Session, SessionList } from "@/sessions/schemas";

export const sid = (n: number): string => `${String(n).repeat(8)}-2222-4333-8444-555555555555`;

export function make(n: number, patch: Partial<Session> = {}): Session {
  const cwd = `/home/kuhy/src/app${String(n)}`;
  return {
    cwd,
    done: false,
    group: 0,
    id: sid(n),
    last_assistant: `A: approve push ${String(n)}\n\n- \`git push\``,
    last_ts: `2026-11-1${String(n)}T08:00:00.000Z`,
    last_user: `prompt ${String(n)}`,
    manual_mark: null,
    mark: "open",
    project: `app${String(n)}`,
    resume_command: `cd '${cwd}' && claude --resume ${sid(n)}`,
    status: "needs_action",
    title: `Session ${String(n)}`,
    ...patch,
  };
}

/** Eight sessions, one per case the page must tell apart, in the server's order. */
export function sessionRows(): Session[] {
  return [
    make(1),
    make(2, { group: 0, last_ts: "2026-11-09T08:00:00.000Z", project: "alpha" }),
    make(3, { group: 1, status: "question", title: "" }),
    make(4, { group: 2, last_ts: null, status: "untagged" }),
    make(5, { group: 3, status: "running" }),
    make(6, { done: true, group: 4, manual_mark: "done", mark: "manual", status: "question" }),
    make(7, { done: true, group: 4, mark: "tag", status: "done" }),
    make(8, { done: true, group: 4, mark: "tag", status: "continuing" }),
  ];
}

export function sessionList(sessions: Session[] = sessionRows()): SessionList {
  return { scan_ms: 4.2, scanned: sessions.length + 3, sessions };
}

export function result(patch: Partial<MutationResult> = {}): MutationResult {
  return { argv: [], ok: true, refused: false, stderr: "", stdout: "", summary: "Done.", ...patch };
}
