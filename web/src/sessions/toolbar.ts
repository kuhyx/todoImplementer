/** Search, status chips, project, idle days, mark and show-done controls. Built once; `sync` refreshes counts and values. */
import type { MarkFilter, Query } from "@/sessions/model";
import type { Session, Status } from "@/sessions/schemas";

import { icon, iconButton } from "@/components/icons";
import { h, must } from "@/lib/dom";
import { label, MARK_ICON, MARK_LABEL, STATUS_ICON, STATUS_LABEL, STATUS_TONE } from "@/sessions/labels";
import { EMPTY_QUERY, projectsOf, statusCounts } from "@/sessions/model";
import { MARKS, STATUSES } from "@/sessions/schemas";

export interface Toolbar {
  el: HTMLElement;
  /** Refresh counts, options and control values from the data and the query. */
  sync: (sessions: readonly Session[], query: Query, shown: number) => void;
}

const MARK_CHOICES: readonly MarkFilter[] = ["all", ...MARKS];

function chip(status: Status, onToggle: (status: Status) => void): HTMLButtonElement {
  const button = h("button", { attrs: { "data-status": status, "data-tone": STATUS_TONE[status], type: "button" }, class: "chip", on: { click: () => { onToggle(status); } } });
  button.append(icon(STATUS_ICON[status]), h("span", { class: "chip-count" }));
  return button;
}

function markChoice(mark: MarkFilter, onPick: (mark: MarkFilter) => void): HTMLButtonElement {
  const name = mark === "all" ? label.filter : MARK_LABEL[mark];
  return iconButton(mark === "all" ? "all" : MARK_ICON[mark], name, { "data-mark": mark }, () => { onPick(mark); });
}

export function renderToolbar(onChange: (next: Query) => void): Toolbar {
  let current: Query = EMPTY_QUERY;
  const change = (patch: Partial<Query>): void => { onChange({ ...current, ...patch }); };
  const search = h("input", { attrs: { "aria-label": label.search, autocomplete: "off", type: "search" }, on: { input: () => { change({ q: search.value }); } } });
  const chips = STATUSES.map((status) => {
    return chip(status, (picked) => {
      const isOn = current.statuses.includes(picked);
      change({ statuses: STATUSES.filter((s) => (s === picked ? !isOn : current.statuses.includes(s))) });
    });
  },
  );
  const project = h("select", { attrs: { "aria-label": label.project }, on: { change: () => { change({ project: project.value }); } } });
  const idle = h("input", { attrs: { "aria-label": label.idleDays, inputmode: "numeric", min: 0, type: "number" }, class: "idle", on: { input: () => {
    const days = Number(idle.value);
    change({ older: idle.value !== "" && days > 0 ? days : null });
  } } });
  const marks = MARK_CHOICES.map((mark) => markChoice(mark, (picked) => { change({ mark: picked }); }));
  const done = iconButton("eye", label.showDone, {}, () => { change({ showDone: !current.showDone }); });
  const reset = iconButton("close", label.reset, {}, () => { onChange(EMPTY_QUERY); });
  const count = h("span", { class: "shown-count" });
  const element = h(
    "div",
    { attrs: { role: "search" }, class: "toolbar" },
    h("label", { class: "search-box" }, icon("search"), search),
    h("div", { class: "chips" }, ...chips),
    h("label", { class: "field" }, icon("folder"), project),
    h("label", { class: "field" }, icon("hourglass"), idle),
    h("div", { class: "marks" }, ...marks),
    done,
    reset,
    count,
  );
  const sync = (sessions: readonly Session[], query: Query, shown: number): void => {
    current = query;
    if (search.value !== query.q) search.value = query.q;
    const counts = statusCounts(sessions);
    for (const button of chips) {
      const status = button.dataset.status as Status;
      const name = `${STATUS_LABEL[status]} (${String(counts[status])})`;
      button.setAttribute("aria-label", name);
      button.title = name;
      button.setAttribute("aria-pressed", String(query.statuses.includes(status)));
      must(button, ".chip-count").textContent = String(counts[status]);
    }
    project.replaceChildren(h("option", { attrs: { value: "" }, text: "—" }), ...projectsOf(sessions, query.project).map((name) => h("option", { attrs: { value: name }, text: name })));
    project.value = query.project;
    idle.value = query.older === null ? "" : String(query.older);
    for (const button of marks) button.setAttribute("aria-pressed", String(button.dataset.mark === query.mark));
    done.setAttribute("aria-pressed", String(query.showDone));
    reset.hidden = JSON.stringify(query) === JSON.stringify(EMPTY_QUERY);
    count.textContent = `${String(shown)}/${String(sessions.length)}`;
  };
  return { el: element, sync };
}
