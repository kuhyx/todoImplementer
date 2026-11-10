import type { ColumnView } from "@/lib/board-model";
import type { ViewState } from "@/lib/hash-state";
import type { ColumnId } from "@/lib/schemas-common";

/** Columns, repo groups and the narrow-screen column tabs. Cards sit where the server put them. */
import { renderCard } from "@/components/card";
import { activeColumn } from "@/lib/board-model";
import { h } from "@/lib/dom";
import { trackHref, trackLink } from "@/track/track-link";

export interface ColumnHandlers {
  onColumn: (id: ColumnId) => void;
  onOpen: (id: string) => void;
}

function countText(column: ColumnView): string {
  return column.shown === column.total ? String(column.total) : `${String(column.shown)} of ${String(column.total)}`;
}

function emptyText(column: ColumnView): string {
  return column.total === 0 ? "Nothing in this column." : "No note here matches the search or repo filter.";
}

/** A group with an empty label is the flat Least-effort list: no heading, the repo goes on each card. */
function renderGroup(group: ColumnView["groups"][number], now: number, state: ViewState, handlers: ColumnHandlers): HTMLElement {
  const isFlat = group.label === "";
  return h(
    "section",
    { attrs: { "aria-label": isFlat ? "Easiest first" : group.label }, class: "group" },
    !isFlat && h("h3", { class: "group-head" }, h("span", { class: "group-name", text: group.label }), h("span", { class: "count", text: String(group.cards.length) })),
    ...group.cards.map((card) => {
      const button = renderCard(card, now, isFlat);
      button.addEventListener("click", () => {
        handlers.onOpen(card.id);
      });
      // An anchor cannot sit inside the card's button: an umbrella card gets a sibling link, outside the click that opens the drawer.
      return card.umbrella === undefined ? button : h("div", { class: "card-wrap" }, button, trackLink(trackHref(state, card.id), "card-track"));
    }),
  );
}

function renderColumn(column: ColumnView, active: ColumnId, now: number, state: ViewState, handlers: ColumnHandlers): HTMLElement {
  return h(
    "section",
    { attrs: { "aria-label": column.label, "data-active": column.id === active, "data-col": column.id }, class: "col" },
    h("header", { class: "col-head" }, h("h2", { text: column.label }), h("span", { class: "count", text: countText(column) })),
    h(
      "div",
      { class: "col-body" },
      ...column.groups.map((group) => renderGroup(group, now, state, handlers)),
      column.groups.length === 0 && h("p", { class: "empty", text: emptyText(column) }),
    ),
  );
}

function renderTabs(view: ColumnView[], active: ColumnId, handlers: ColumnHandlers): HTMLElement {
  return h(
    "nav",
    { attrs: { "aria-label": "Columns" }, class: "tabs" },
    ...view.map((column) => {
      return h(
        "button",
        {
          attrs: { "aria-current": column.id === active ? "true" : null, "data-col": column.id, type: "button" },
          class: "tab",
          on: {
            click: () => {
              handlers.onColumn(column.id);
            },
          },
        },
        h("span", { class: "tab-label", text: column.label }),
        h("span", { class: "count", text: countText(column) }),
      );
    },
    ),
  );
}

export function renderBoard(view: ColumnView[], state: ViewState, now: number, handlers: ColumnHandlers): HTMLElement {
  const active = activeColumn(view, state);
  return h(
    "div",
    { class: "board" },
    renderTabs(view, active, handlers),
    h("div", { class: "cols" }, ...view.map((column) => renderColumn(column, active, now, state, handlers))),
  );
}
