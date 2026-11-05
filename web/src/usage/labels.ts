export const label = {
  all: "all",
  brand: "todoImplementer",
  directory: "Directory",
  empty: "No rows match.",
  filter: "Filter",
  from: "From",
  loading: "Loading",
  model: "Model",
  none: "none",
  reset: "Reset",
  scope: "Scope",
  search: "Search",
  searchHint: "Search (fuzzy)",
  showAll: "Show all",
  showFirst: "Show first",
  table: "Table view",
  title: "Token usage",
  to: "To",
  views: "Usage views",
  window: "Snapshot window",
} as const;

export const countText = (visible: number, matched: number, total: number): string =>
  matched === total ? `${String(visible)} / ${String(total)}` : `${String(visible)} / ${String(matched)} (${String(total)})`;
