import type { Board } from "@/lib/schemas";

/** Search, repo filter and sort. Built once and updated in place so typing is never interrupted by a poll. */
import { repoOptions } from "@/lib/board-model";
import { h } from "@/lib/dom";
import { type Sort, SORTS, type ViewState } from "@/lib/hash-state";

export interface ToolbarHandlers {
  onChange: (patch: Partial<Pick<ViewState, "q" | "repo" | "sort">>) => void;
}

export interface Toolbar {
  el: HTMLElement;
  update: (board: Board, state: ViewState) => void;
}

const SORT_LABEL: Record<Sort, string> = {
  cost: "Cost",
  effort: "Least effort",
  priority: "Priority",
  title: "Title",
  updated: "Recently updated",
};

function field(label: string, control: HTMLElement): HTMLElement {
  return h("label", { class: "field" }, h("span", { class: "field-label", text: label }), control);
}

export function createToolbar(handlers: ToolbarHandlers): Toolbar {
  const search = h("input", {
    attrs: { autocomplete: "off", name: "q", placeholder: "Search title, repo, id", type: "search" },
    on: {
      input: () => {
        handlers.onChange({ q: search.value });
      },
    },
  });
  const repository = h("select", {
    attrs: { name: "repo" },
    on: {
      change: () => {
        handlers.onChange({ repo: repository.value });
      },
    },
  });
  const sort = h(
    "select",
    {
      attrs: { name: "sort" },
      on: {
        change: () => {
          handlers.onChange({ sort: SORTS.find((candidate) => candidate === sort.value) ?? "priority" });
        },
      },
    },
    ...SORTS.map((id) => h("option", { attrs: { value: id }, text: SORT_LABEL[id] })),
  );
  const clear = h("button", {
    attrs: { type: "button" },
    class: "btn",
    on: {
      click: () => {
        handlers.onChange({ q: "", repo: "" });
        search.focus();
      },
    },
    text: "Clear filters",
  });
  const element = h("div", { attrs: { role: "search" }, class: "toolbar" }, field("Search", search), field("Repo", repository), field("Sort", sort), clear);

  const update = (board: Board, state: ViewState): void => {
    const options = repoOptions(board);
    const isKnown = options.some((option) => option.value === state.repo);
    const signature = options.map((option) => `${option.value}:${String(option.count)}`).join("|");
    if (!isKnown || repository.dataset.sig !== signature) {
      repository.replaceChildren(
        ...options.map((option) =>
          h("option", { attrs: { value: option.value }, text: `${option.label} (${String(option.count)})` }),
        ),
        ...(isKnown ? [] : [h("option", { attrs: { value: state.repo }, text: `${state.repo} (no open notes)` })]),
      );
      repository.dataset.sig = signature;
    }
    repository.value = state.repo;
    sort.value = state.sort;
    if (document.activeElement !== search) search.value = state.q;
    clear.hidden = state.q === "" && state.repo === "";
  };
  return { el: element, update };
}
