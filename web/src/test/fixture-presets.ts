/**
 * Per-status card presets for fixtures and the dev mock. This mirrors what the
 * server sends (DOCS-spec.md "Actions"); the page never imports it, so it
 * cannot leak status logic into the product code.
 */
import type { Action, TaskCard } from "@/lib/schemas-common";

export type Preset = Pick<TaskCard, "actions" | "column" | "current" | "needs" | "stage" | "status">;

const RESUME: Action = { enabled: true, id: "copy-resume", label: "Copy resume command", reason: null, value: "cd /tmp/wt && claude --resume 0b1c2d3e" };
const CANCEL: Action = { confirm: true, enabled: true, id: "cancel", label: "Cancel run", reason: null };
const SEND: Action = { enabled: true, id: "send", label: "Send to Claude", reason: null };

export function preset(status: TaskCard["status"], hasRepository: boolean): Preset {
  const start: Action = {
    enabled: hasRepository,
    id: "start",
    label: "Start",
    reason: hasRepository ? null : "This note has no repo, so it stays yours",
  };
  switch (status) {
    case "backlog":
    case "yours": {
      return { actions: [start], column: "backlog", current: status === "yours" ? "Yours" : "Not started", needs: null, stage: null, status };
    }
    case "cancelled": {
      return { actions: [start], column: "backlog", current: "Cancelled; run dir kept", needs: null, stage: "cancelled", status };
    }
    case "done": {
      return { actions: [], column: "done", current: "shipped", needs: null, stage: "shipped", status };
    }
    case "needs_you": {
      return {
        actions: [
          { enabled: true, id: "spec-answers", label: "Save answers", reason: null },
          { enabled: false, id: "spec-ok", label: "Spec OK", reason: "2 questions are still unanswered" },
          CANCEL,
        ],
        column: "needs_you",
        current: "waiting for your answers",
        needs: { kind: "spec_questions", text: "Answer 2 questions so Claude can plan." },
        stage: "spec_wait",
        status,
      };
    }
    case "paused_limit": {
      return {
        actions: [
          { confirm: true, enabled: true, id: "credits", label: "Run on credits", reason: null },
          CANCEL,
        ],
        column: "running",
        current: "paused: 5 h plan limit",
        needs: null,
        stage: "paused_limit",
        status,
      };
    }
    case "queued": {
      return { actions: [CANCEL], column: "running", current: "waiting to start", needs: null, stage: "implement", status };
    }
    case "ready_to_ship": {
      return {
        actions: [
          { confirm: true, enabled: true, id: "ship", label: "Ship", reason: null },
          SEND,
          RESUME,
          { enabled: true, id: "lesson-approve", label: "Approve lesson", reason: null },
        ],
        column: "ready",
        current: "checks green, ready for your click",
        needs: null,
        stage: "gate",
        status,
      };
    }
    case "shipping": {
      return { actions: [], column: "running", current: "rebasing on origin/main", needs: null, stage: "shipping", status };
    }
    case "working": {
      return { actions: [SEND, CANCEL, RESUME], column: "running", current: "implementing: step 2 of 4", needs: null, stage: "implement", status };
    }
  }
}
