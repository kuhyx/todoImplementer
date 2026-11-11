/** Accessible names only: the page shows icons and numbers, these words live in `title` and `aria-label` (textgate). */
import type { IconName } from "@/components/icons";
import type { Mark, Status } from "@/sessions/schemas";

export const STATUS_LABEL: Record<Status, string> = {
  continuing: "continuing in a new session",
  done: "done",
  needs_action: "needs action",
  question: "question",
  running: "running",
  untagged: "no status tag",
};

export const STATUS_ICON: Record<Status, IconName> = {
  continuing: "continuing",
  done: "done",
  needs_action: "attention",
  question: "question",
  running: "running",
  untagged: "untagged",
};

/** The semantic token each status draws in: what wants kuhy is danger, unknown is warning, live work is info, finished is muted. */
export const STATUS_TONE: Record<Status, string> = {
  continuing: "muted",
  done: "muted",
  needs_action: "danger",
  question: "danger",
  running: "info",
  untagged: "warning",
};

export const MARK_LABEL: Record<Mark, string> = { manual: "marked done by hand", open: "not done", tag: "done by its status tag" };
export const MARK_ICON: Record<Mark, IconName> = { manual: "person", open: "circle", tag: "tag" };

export const COLUMN_LABEL = {
  age: "idle time",
  group: "status",
  markRank: "done mark",
  project: "project",
  title: "title",
} as const;

export const COLUMN_ICON: Record<keyof typeof COLUMN_LABEL, IconName> = {
  age: "queued",
  group: "circle",
  markRank: "check",
  project: "folder",
  title: "all",
};

export const label = {
  armed: "click again to move to the trash",
  clearSelection: "clear the selection",
  copy: "copy the resume command",
  copyAll: "copy the resume commands",
  copyFailed: "the clipboard is not available",
  delete: "move to the trash",
  details: "details",
  filter: "filter",
  idleDays: "idle for more than this many days",
  loading: "reading the session transcripts",
  mark: "mark done",
  noToken: "the page has no CSRF token; reload it from the server",
  project: "project",
  reload: "load again",
  reset: "reset the filters",
  resume: "resume in a terminal",
  resumeMax: "at most 5 terminals at once",
  search: "search",
  select: "select",
  selectAll: "select all",
  showDone: "show done sessions",
  table: "sessions",
  unmark: "remove the done mark",
} as const;
