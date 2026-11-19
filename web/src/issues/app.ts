/** <issues-app>: loads and polls one task's issue log, keeps task + filters + sort in the hash, wires toolbar and table. */
import type { Query } from "@/issues/model";
import type { Issue } from "@/issues/schemas";

import { icon, iconButton } from "@/components/icons";
import { loadIssues } from "@/issues/api";
import { label } from "@/issues/labels";
import { readQuery, visibleIssues, writeQuery } from "@/issues/model";
import { renderTable, type SortName } from "@/issues/table";
import { renderToolbar } from "@/issues/toolbar";
import { h } from "@/lib/dom";
import { errorText } from "@/lib/http";
import { poll } from "@/lib/poller";
import { cycleSort } from "@/usage/table-model";

export const POLL_MS = 5000;

/** What the last load found: the issues, an unknown task, or still nothing. */
type Data = { issues: Issue[]; kind: "issues" } | { kind: "loading" } | { kind: "unknown" };

export class IssuesApp extends HTMLElement {
  #data: Data = { kind: "loading" };
  #error: null | string = null;
  readonly #host = h("main", { attrs: { "aria-live": "polite" }, class: "main" });
  readonly #back = h("a", { attrs: { "aria-label": label.back, title: label.back }, class: "icon-btn btn back" }, icon("back"));
  readonly #taskId = h("code", { class: "task-id" });
  #query: Query = readQuery("");
  #signature = "";
  #stop: (() => void) | undefined;
  readonly #toolbar = renderToolbar((next) => { this.#setQuery(next); });

  readonly #onHash = (): void => {
    const task = this.#query.task;
    this.#query = readQuery(globalThis.location.hash);
    if (task === this.#query.task) {
      this.#render();
      return;
    }
    this.#data = { kind: "loading" };
    this.#signature = "";
    this.#render();
    void this.#refresh();
  };

  readonly #refresh = async (): Promise<void> => {
    const task = this.#query.task;
    if (task === "") return;
    try {
      const issues = await loadIssues(task);
      const signature = JSON.stringify(issues);
      // An unchanged log keeps the DOM as it is: the scroll, a focused control and a half-typed search survive the poll.
      if (signature === this.#signature && this.#error === null) return;
      this.#signature = signature;
      this.#data = issues === null ? { kind: "unknown" } : { issues, kind: "issues" };
      this.#error = null;
    } catch (error) {
      this.#error = errorText(error);
    }
    this.#render();
  };

  #setQuery(next: Query): void {
    this.#query = next;
    globalThis.history.replaceState(null, "", `${globalThis.location.pathname}${globalThis.location.search}${writeQuery(next)}`);
    this.#render();
  }

  #sort(key: SortName, isExtend: boolean): void {
    this.#setQuery({ ...this.#query, sort: cycleSort(this.#query.sort, key, isExtend) });
  }

  #state(glyph: "done" | "failed", name: string): HTMLElement {
    return h("p", { attrs: { "aria-label": name, role: glyph === "failed" ? "alert" : "status", title: name }, class: `state-${glyph}` }, icon(glyph));
  }

  #body(): HTMLElement[] {
    if (this.#query.task === "") return [this.#state("failed", label.noTask)];
    const data = this.#data;
    if (data.kind === "unknown") return [this.#state("failed", label.unknown)];
    if (data.kind === "loading") {
      return this.#error === null ? [h("span", { attrs: { "aria-label": label.loading, role: "progressbar", title: label.loading }, class: "spinner" })] : [];
    }
    if (data.issues.length === 0) return [this.#state("done", label.empty)];
    const items = visibleIssues(data.issues, this.#query);
    this.#toolbar.sync(data.issues, this.#query, items.length);
    return [renderTable({ items, nowMs: Date.now(), onSort: (key, isExtend) => { this.#sort(key, isExtend); }, query: this.#query })];
  }

  #render(): void {
    const top = this.#host.scrollTop;
    const { task } = this.#query;
    this.#taskId.textContent = task;
    this.#back.setAttribute("href", task === "" ? "/" : `/#task=${encodeURIComponent(task)}`);
    this.#toolbar.el.hidden = this.#data.kind !== "issues" || this.#data.issues.length === 0;
    if (this.#data.kind !== "issues") this.#toolbar.sync([], this.#query, 0);
    const failure = this.#error === null ? [] : [this.#failure(this.#error)];
    this.#host.replaceChildren(...failure, ...this.#body());
    this.#host.scrollTop = top;
  }

  #failure(message: string): HTMLElement {
    const retry = iconButton("retry", label.reload, {}, () => { void this.#refresh(); });
    return h("p", { attrs: { "aria-label": message, role: "alert", title: message }, class: "failure" }, icon("failed"), retry);
  }

  connectedCallback(): void {
    this.#query = readQuery(globalThis.location.hash);
    this.replaceChildren(h("header", { class: "head" }, this.#back, icon("issue"), this.#taskId), this.#toolbar.el, this.#host);
    globalThis.addEventListener("hashchange", this.#onHash);
    this.#render();
    this.#stop = poll(this.#refresh, POLL_MS);
  }

  disconnectedCallback(): void {
    globalThis.removeEventListener("hashchange", this.#onHash);
    this.#stop?.();
  }
}

export function defineIssues(): void {
  if (customElements.get("issues-app") === undefined) customElements.define("issues-app", IssuesApp);
}
