/** <sessions-app>: loads and polls the list, keeps the query in the hash, and wires the toolbar, the bulk bar and the table. */
import type { Action } from "@/sessions/api";
import type { Item, Query } from "@/sessions/model";
import type { Outcome } from "@/sessions/parts";
import type { MutationResult, SessionList } from "@/sessions/schemas";

import { icon, iconButton } from "@/components/icons";
import { csrfToken } from "@/lib/boot";
import { h } from "@/lib/dom";
import { errorText } from "@/lib/http";
import { poll } from "@/lib/poller";
import { bulkBar, type Perform } from "@/sessions/actions";
import { loadSessions, postSessions } from "@/sessions/api";
import { label } from "@/sessions/labels";
import { EMPTY_QUERY, readQuery, selectedIds, visibleItems, writeQuery } from "@/sessions/model";
import { DISARM } from "@/sessions/parts";
import { renderTable, type SortName } from "@/sessions/table";
import { renderToolbar } from "@/sessions/toolbar";
import { cycleSort } from "@/usage/table-model";

export const POLL_MS = 10_000;
const BULK = "bulk";

function outcomeKind(result: MutationResult): Outcome["kind"] {
  if (result.ok) return "ok";
  return result.refused ? "refused" : "failed";
}

export class SessionsApp extends HTMLElement {
  #anchor: null | string = null;
  #busy = false;
  #data: null | SessionList = null;
  #error: null | string = null;
  #isDeferred = false;
  #items: Item[] = [];
  readonly #host = h("main", { attrs: { "aria-live": "polite" }, class: "main" });
  #open = new Set<string>();
  #outcomes = new Map<string, Outcome>();
  #query: Query = EMPTY_QUERY;
  #selected = new Set<string>();
  #signature = "";
  #stop: (() => void) | undefined;
  readonly #toolbar = renderToolbar((next) => { this.#setQuery(next); });

  readonly #onHash = (): void => {
    this.#query = readQuery(globalThis.location.hash);
    this.#render();
  };

  readonly #refresh = async (): Promise<void> => {
    try {
      const list = await loadSessions();
      const signature = JSON.stringify(list.sessions);
      // An unchanged list keeps the DOM as it is, so an armed delete or a half-typed filter survives the poll.
      if (signature === this.#signature && this.#error === null) return;
      this.#signature = signature;
      this.#data = list;
      this.#error = null;
    } catch (error) {
      this.#error = errorText(error);
    }
    // A redraw would disarm a delete or drop the focus: hold it back until neither is in play (`#applyHeld`).
    if (this.#isHeld()) this.#isDeferred = true;
    else this.#render();
  };

  readonly #applyHeld = (): void => {
    if (this.#isDeferred && !this.#isHeld()) this.#render();
  };

  readonly #perform: Perform = async (action: Action, body: Record<string, unknown>, key: string) => {
    const csrf = csrfToken();
    if (csrf === null) {
      this.#outcomes.set(key, { kind: "failed", summary: label.noToken });
      this.#render();
      return;
    }
    this.#busy = true;
    this.#outcomes.delete(key);
    this.#render();
    let outcome: Outcome;
    try {
      const result = await postSessions(action, body, csrf);
      outcome = { kind: outcomeKind(result), summary: [result.summary, result.ok ? "" : result.stderr].filter(Boolean).join("\n") };
      if (action !== "resume" && result.ok) {
        if (key === BULK) this.#selected.clear();
        this.#signature = "";
        await this.#refresh();
      }
    } catch (error) {
      outcome = { kind: "failed", summary: errorText(error) };
    }
    this.#busy = false;
    this.#outcomes.set(key, outcome);
    this.#render();
  };

  #setQuery(next: Query): void {
    this.#query = next;
    globalThis.history.replaceState(null, "", `${globalThis.location.pathname}${globalThis.location.search}${writeQuery(next)}`);
    this.#render();
  }

  #select(id: string, isRange: boolean): void {
    const ids = this.#items.map((item) => item.id);
    const from = this.#anchor === null ? -1 : ids.indexOf(this.#anchor);
    if (isRange && from >= 0) {
      const to = ids.indexOf(id);
      const range = ids.slice(Math.min(from, to), Math.max(from, to) + 1);
      for (const picked of range) this.#selected.add(picked);
    } else if (this.#selected.has(id)) this.#selected.delete(id);
    else this.#selected.add(id);
    this.#anchor = id;
    this.#render();
  }

  #selectAll(): void {
    const isAll = this.#items.every((item) => this.#selected.has(item.id));
    this.#selected = new Set(isAll ? [] : this.#items.map((item) => item.id));
    this.#render();
  }

  #toggle(id: string): void {
    if (!this.#open.delete(id)) this.#open.add(id);
    this.#render();
  }

  #sort(key: SortName, isExtend: boolean): void {
    this.#setQuery({ ...this.#query, sort: cycleSort(this.#query.sort, key, isExtend) });
  }

  /** An armed delete, or the focus on a control of the table or bulk bar: what a redraw would destroy. */
  #isHeld(): boolean {
    return this.#host.querySelector("[data-armed]") !== null || this.#host.contains(document.activeElement);
  }

  #render(): void {
    this.#isDeferred = false;
    const top = this.#host.scrollTop;
    const data = this.#data;
    this.#toolbar.sync(data?.sessions ?? [], this.#query, 0);
    if (data === null) {
      this.#host.replaceChildren(this.#error === null ? h("span", { attrs: { "aria-label": label.loading, role: "progressbar", title: label.loading }, class: "spinner" }) : this.#failure(this.#error));
      return;
    }
    const nowMs = Date.now();
    this.#items = visibleItems(data.sessions, this.#query, nowMs);
    this.#selected = this.#selected.intersection(new Set(data.sessions.map((session) => session.id)));
    this.#toolbar.sync(data.sessions, this.#query, this.#items.length);
    const ids = selectedIds(this.#selected, this.#items);
    const isBulk = ids.length > 0 || this.#outcomes.has(BULK);
    const commands = (): string => this.#items.filter((item) => this.#selected.has(item.id)).map((item) => item.resume_command).join("\n");
    this.#host.replaceChildren(
      ...[
        this.#error !== null && this.#failure(this.#error),
        isBulk && bulkBar({ commands, ids, isBusy: this.#busy, onClear: () => { this.#clearSelection(); }, outcome: this.#outcomes.get(BULK) }, this.#perform),
        renderTable({
          isBusy: this.#busy,
          items: this.#items,
          nowMs,
          onSelect: (id, isRange) => { this.#select(id, isRange); },
          onSelectAll: () => { this.#selectAll(); },
          onSort: (key, isExtend) => { this.#sort(key, isExtend); },
          onToggle: (id) => { this.#toggle(id); },
          open: this.#open,
          outcomes: this.#outcomes,
          perform: this.#perform,
          query: this.#query,
          selected: this.#selected,
        }),
      ].filter((part) => part !== false),
    );
    this.#host.scrollTop = top;
  }

  #clearSelection(): void {
    this.#selected.clear();
    this.#outcomes.delete(BULK);
    this.#render();
  }

  #failure(message: string): HTMLElement {
    const retry = iconButton("retry", label.reload, {}, () => { void this.#refresh(); });
    return h("p", { attrs: { "aria-label": message, role: "alert", title: message }, class: "failure" }, icon("failed"), retry);
  }

  connectedCallback(): void {
    this.#query = readQuery(globalThis.location.hash);
    const back = h("a", { attrs: { "aria-label": "todoImplementer", href: "/", title: "todoImplementer" }, class: "icon-btn btn back" });
    back.append(icon("back"));
    this.replaceChildren(h("header", { class: "head" }, back), this.#toolbar.el, this.#host);
    globalThis.addEventListener("hashchange", this.#onHash);
    this.#host.addEventListener("focusout", () => { setTimeout(this.#applyHeld, 0); });
    this.#host.addEventListener(DISARM, this.#applyHeld);
    this.#render();
    this.#stop = poll(this.#refresh, POLL_MS);
  }

  disconnectedCallback(): void {
    globalThis.removeEventListener("hashchange", this.#onHash);
    this.#stop?.();
  }
}

export function defineSessions(): void {
  if (customElements.get("sessions-app") === undefined) customElements.define("sessions-app", SessionsApp);
}
