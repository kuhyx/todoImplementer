/** View state in the URL hash (R3); defaults are omitted. */
import { COLUMN_IDS, type ColumnId } from "@/lib/schemas-common";

export const SORTS = ["effort", "priority", "updated", "title", "cost"] as const;
export type Sort = (typeof SORTS)[number];

export const YOURS = "-";

export interface ViewState {
  /** null = no tab chosen: the board picks the first column that has cards (see activeColumn). */
  col: ColumnId | null;
  q: string;
  repo: string;
  sort: Sort;
  task: null | string;
  /** The umbrella whose tracking view replaces the board (`#umbrella=<card id>`). */
  umbrella: null | string;
}

export const DEFAULT_STATE: ViewState = { col: null, q: "", repo: "", sort: "effort", task: null, umbrella: null };

const isCardId = (value: null | string): value is string => value !== null && /^[A-Za-z0-9]{8}-\d+$/v.test(value);

function oneOf<T extends string>(allowed: readonly T[], value: null | string, fallback: T): T {
  return allowed.find((candidate) => candidate === value) ?? fallback;
}

export function parseHash(hash: string): ViewState {
  const parameters = new URLSearchParams(hash.replace(/^#/v, ""));
  const task = parameters.get("task");
  const umbrella = parameters.get("umbrella");
  return {
    col: COLUMN_IDS.find((candidate) => candidate === parameters.get("col")) ?? null,
    q: parameters.get("q") ?? "",
    repo: parameters.get("repo") ?? "",
    sort: oneOf(SORTS, parameters.get("sort"), DEFAULT_STATE.sort),
    task: isCardId(task) ? task : null,
    umbrella: isCardId(umbrella) ? umbrella : null,
  };
}

export function formatHash(state: ViewState): string {
  const parameters = new URLSearchParams();
  if (state.repo !== "") parameters.set("repo", state.repo);
  if (state.q !== "") parameters.set("q", state.q);
  if (state.sort !== DEFAULT_STATE.sort) parameters.set("sort", state.sort);
  if (state.col !== null) parameters.set("col", state.col);
  if (state.task !== null) parameters.set("task", state.task);
  if (state.umbrella !== null) parameters.set("umbrella", state.umbrella);
  const text = parameters.toString();
  return text === "" ? "" : `#${text}`;
}
