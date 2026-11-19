/** Accessible names only: the page shows icons, numbers and the log's own text; these words live in `title` and `aria-label` (textgate). */
import type { IconName } from "@/components/icons";
import type { StateFilter } from "@/issues/model";
import type { SORT_KEYS } from "@/issues/model";

type SortName = (typeof SORT_KEYS)[number];

export const STATE_LABEL: Record<StateFilter, string> = {
  all: "all issues",
  fixed: "fixed by the manager",
  open: "not fixed",
  raw: "line that is not an issue record",
};

export const STATE_ICON: Record<StateFilter, IconName> = { all: "issue", fixed: "check", open: "circle", raw: "log" };

/** The semantic token each state draws in: fixed is success, open is warning, a raw line is muted. */
export const STATE_TONE: Record<StateFilter, string> = { all: "info", fixed: "success", open: "warning", raw: "muted" };

export const COLUMN_LABEL: Record<SortName, string> = {
  action: "what the manager did",
  child: "repo",
  model: "model",
  phase: "phase",
  state: "fixed",
  symptom: "symptom",
  ts: "time",
};

export const COLUMN_ICON: Record<SortName, IconName> = {
  action: "terminal",
  child: "folder",
  model: "robot",
  phase: "tag",
  state: "fixed",
  symptom: "failed",
  ts: "queued",
};

export const label = {
  back: "the card on the board",
  empty: "no issues logged",
  loading: "loading the issue log",
  model: "model",
  noModel: "no model",
  noTask: "no task id in the address",
  phase: "phase",
  raw: "raw issue log (ndjson)",
  reload: "reload",
  repo: "repo",
  reset: "clear filters",
  search: "search",
  table: "free-model issues",
  unknown: "the server knows no such task",
} as const;
