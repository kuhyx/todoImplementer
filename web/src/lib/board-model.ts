/**
 * Board -> what to draw. Cards sit in the column the server put them in
 * (`card.column`); this file only filters, sorts and groups. It never derives
 * a status.
 */
import { fuzzyMatch } from "@kuhyx/web-ui";

import type { Board } from "@/lib/schemas";
import type { ColumnId, TaskCard } from "@/lib/schemas-common";

import { type Sort, type ViewState, YOURS } from "@/lib/hash-state";

export interface Group {
  cards: TaskCard[];
  label: string;
  repo: null | string;
}

export interface ColumnView {
  groups: Group[];
  id: ColumnId;
  label: string;
  shown: number;
  total: number;
}

export interface RepoOption {
  count: number;
  label: string;
  value: string;
}

const PRIORITY_RANK: Record<string, number> = { high: 1, low: 3, medium: 2, normal: 2, urgent: 0 };
const UNKNOWN_RANK = 4;

export function searchText(card: TaskCard): string {
  return [card.title, card.repo ?? "yours", card.id, card.current, card.needs?.text ?? ""].join(" ");
}

function matchesQuery(card: TaskCard, query: string): boolean {
  const words = query.split(/\s+/v).filter(Boolean);
  const text = searchText(card);
  return words.every((word) => fuzzyMatch(word, text));
}

function matchesRepository(card: TaskCard, repository: string): boolean {
  if (repository === "") return true;
  return repository === YOURS ? card.repo === null : card.repo === repository;
}

const COMPARE: Record<Sort, (a: TaskCard, b: TaskCard) => number> = {
  cost: (a, b) => b.cost_usd - a.cost_usd,
  effort: (a, b) => {
    return Number(a.needs?.category !== "questions") - Number(b.needs?.category !== "questions") ||
    (a.needs?.effort ?? 0) - (b.needs?.effort ?? 0) ||
    COMPARE.priority(a, b);
  },
  priority: (a, b) =>
    (PRIORITY_RANK[a.priority] ?? UNKNOWN_RANK) - (PRIORITY_RANK[b.priority] ?? UNKNOWN_RANK),
  title: (a, b) => a.title.localeCompare(b.title),
  updated: (a, b) => (b.updated ?? 0) - (a.updated ?? 0),
};

export function sortCards(cards: TaskCard[], sort: Sort): TaskCard[] {
  const primary = COMPARE[sort];
  return cards.toSorted(
    (a, b) => primary(a, b) || COMPARE.updated(a, b) || a.title.localeCompare(b.title) || a.id.localeCompare(b.id),
  );
}

/** Yours first, then repos A-Z. */
function compareGroups(a: Group, b: Group): number {
  return Number(b.repo === null) - Number(a.repo === null) || a.label.localeCompare(b.label);
}

/** Least effort is one unlabelled list across repos; every other sort groups by repo. */
function group(cards: TaskCard[], sort: Sort): Group[] {
  if (sort === "effort") return cards.length === 0 ? [] : [{ cards: sortCards(cards, sort), label: "", repo: null }];
  const byRepository = new Map<null | string, TaskCard[]>();
  for (const card of cards) byRepository.set(card.repo, [...(byRepository.get(card.repo) ?? []), card]);
  return [...byRepository]
    .map(([repository, members]) => ({ cards: sortCards(members, sort), label: repository ?? "Yours", repo: repository }))
    .toSorted(compareGroups);
}

export function buildView(board: Board, state: ViewState): ColumnView[] {
  const visible = board.tasks.filter((card) => matchesRepository(card, state.repo) && matchesQuery(card, state.q));
  return board.columns.map((column) => {
    return {
      groups: group(
        visible.filter((card) => card.column === column.id),
        state.sort,
      ),
      id: column.id,
      label: column.label,
      shown: visible.filter((card) => card.column === column.id).length,
      total: column.count,
    };
  });
}

/** The tab shown: the hash choice, else Needs you if it has cards, else the first non-empty column, else Backlog. */
export function activeColumn(view: ColumnView[], state: ViewState): ColumnId {
  if (state.col !== null) return state.col;
  const isFilled = (column: ColumnView): boolean => column.shown > 0;
  return (view.find((column) => column.id === "needs_you" && isFilled(column)) ?? view.find((column) => isFilled(column)))?.id ?? "backlog";
}

/** All, Yours (only when some note has no repo), then each repo with its card count. */
export function repoOptions(board: Board): RepoOption[] {
  const count = (repository: null | string): number => board.tasks.filter((card) => card.repo === repository).length;
  const yours = count(null);
  return [
    { count: board.tasks.length, label: "All repos", value: "" },
    ...(yours > 0 ? [{ count: yours, label: "Yours (no repo)", value: YOURS }] : []),
    ...board.repos.map((repository) => ({ count: count(repository), label: repository, value: repository })),
  ];
}
