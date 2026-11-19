/** Search, fixed/open chips, phase and model chips (the log's own words), repo picker, reset and the shown count. */
import type { Query, StateFilter, Tally } from "@/issues/model";
import type { Issue } from "@/issues/schemas";

import { icon, iconButton } from "@/components/icons";
import { label, STATE_ICON, STATE_LABEL, STATE_TONE } from "@/issues/labels";
import { EMPTY_QUERY, STATE_FILTERS, stateCounts, tally } from "@/issues/model";
import { h } from "@/lib/dom";
import { routes } from "@/lib/routes";

export interface Toolbar {
  el: HTMLElement;
  /** Refresh counts, chips and control values from the issues and the query. */
  sync: (issues: readonly Issue[], query: Query, shown: number) => void;
}

type Change = (patch: Partial<Query>) => void;

function stateChip(state: StateFilter, count: number, query: Query, change: Change): HTMLButtonElement {
  const name = `${STATE_LABEL[state]} (${String(count)})`;
  return h(
    "button",
    {
      attrs: { "aria-label": name, "aria-pressed": query.state === state, "data-state": state, "data-tone": STATE_TONE[state], title: name, type: "button" },
      class: "chip",
      on: { click: () => { change({ state }); } },
    },
    icon(STATE_ICON[state]),
    h("span", { class: "chip-count", text: String(count) }),
  );
}

/** One chip per value; a click picks it, a second click on the picked one clears it. */
function valueChips(key: "model" | "phase", values: Tally, query: Query, change: Change): HTMLElement {
  const chips = values.map(([value, count]) => {
    const name = `${label[key]} ${value} (${String(count)})`;
    return h(
      "button",
      {
        attrs: { "aria-label": name, "aria-pressed": query[key] === value, "data-value": value, title: name, type: "button" },
        class: "chip value-chip",
        on: { click: () => { change({ [key]: query[key] === value ? "" : value }); } },
      },
      h("code", { text: value }),
      h("span", { class: "chip-count", text: String(count) }),
    );
  });
  return h("div", { attrs: { "aria-label": label[key], "data-key": key, role: "group" }, class: "chips" }, icon(key === "phase" ? "tag" : "robot"), ...chips);
}

export function renderToolbar(onChange: (next: Query) => void): Toolbar {
  let current: Query = EMPTY_QUERY;
  const change: Change = (patch) => { onChange({ ...current, ...patch }); };
  const search = h("input", { attrs: { "aria-label": label.search, autocomplete: "off", type: "search" }, on: { input: () => { change({ q: search.value }); } } });
  const states = h("div", { attrs: { role: "group" }, class: "chips states" });
  const phases = h("div", { class: "chip-slot" });
  const models = h("div", { class: "chip-slot" });
  const repo = h("select", { attrs: { "aria-label": label.repo }, on: { change: () => { change({ repo: repo.value }); } } });
  const reset = iconButton("close", label.reset, {}, () => { onChange({ ...EMPTY_QUERY, task: current.task }); });
  const raw = h("a", { attrs: { "aria-label": label.raw, download: "", title: label.raw }, class: "btn icon-btn raw-link" }, icon("install"));
  const count = h("span", { class: "shown-count" });
  const element = h(
    "div",
    { attrs: { role: "search" }, class: "toolbar" },
    h("label", { class: "search-box" }, icon("search"), search),
    states,
    phases,
    models,
    h("label", { class: "field" }, icon("folder"), repo),
    reset,
    raw,
    count,
  );
  const sync = (issues: readonly Issue[], query: Query, shown: number): void => {
    current = query;
    if (search.value !== query.q) search.value = query.q;
    const counts = stateCounts(issues);
    states.replaceChildren(...STATE_FILTERS.filter((state) => state !== "raw" || counts.raw > 0).map((state) => stateChip(state, counts[state], query, change)));
    phases.replaceChildren(valueChips("phase", tally(issues, "phase"), query, change));
    models.replaceChildren(valueChips("model", tally(issues, "model"), query, change));
    const repos = tally(issues, "child").map(([name]) => name).toSorted((a, b) => a.localeCompare(b));
    if (query.repo !== "" && !repos.includes(query.repo)) repos.push(query.repo);
    repo.replaceChildren(h("option", { attrs: { value: "" }, text: "—" }), ...repos.map((name) => h("option", { attrs: { value: name }, text: name })));
    repo.value = query.repo;
    raw.setAttribute("href", query.task === "" ? "#" : routes.issues(query.task));
    reset.hidden = JSON.stringify({ ...query, task: "" }) === JSON.stringify(EMPTY_QUERY);
    count.textContent = `${String(shown)}/${String(issues.length)}`;
  };
  return { el: element, sync };
}
