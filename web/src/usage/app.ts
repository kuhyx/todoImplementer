/** <usage-app>: tabs, global filters and the current view. All state is the URL hash, so every view is linkable. */
import type { Context } from "@/usage/context";
import type { TokensIndex } from "@/usage/schemas";

import { h } from "@/lib/dom";
import { loadIndex } from "@/usage/api";
import { hashContext } from "@/usage/context";
import { filterBar } from "@/usage/filter-bar";
import { label } from "@/usage/labels";
import { formatRoute, parseRoute, type Route, tabFor, type ViewId, VIEWS } from "@/usage/route";
import { abView } from "@/usage/view-ab";
import { anomaliesView } from "@/usage/view-anomalies";
import { autonomyView } from "@/usage/view-autonomy";
import { contextView } from "@/usage/view-context";
import { efficiencyView } from "@/usage/view-efficiency";
import { fileView } from "@/usage/view-file";
import { itemsView } from "@/usage/view-items";
import { leversView } from "@/usage/view-levers";
import { genericView, moreIndexView } from "@/usage/view-more";
import { overviewView } from "@/usage/view-overview";
import { sessionView } from "@/usage/view-session";
import { sessionsView } from "@/usage/view-sessions";

export const REFRESH_MS = 60_000;

type Render = (context: Context, signal: AbortSignal, argument: string) => Promise<HTMLElement>;

const RENDERERS: Record<ViewId, Render> = {
  ab: abView,
  anomalies: anomaliesView,
  autonomy: autonomyView,
  context: contextView,
  efficiency: efficiencyView,
  f: (context, signal, argument) => fileView(context, signal, argument),
  items: itemsView,
  levers: leversView,
  more: (context, signal, argument) => (argument === "" ? moreIndexView(context, signal) : genericView(context, signal, argument)),
  overview: overviewView,
  s: (context, signal, argument) => sessionView(context, signal, argument),
  sessions: sessionsView,
};

const errorText = (error: unknown): string => (error as Error).message;

export class UsageApp extends HTMLElement {
  private abort = new AbortController();
  private readonly main = h("main", { attrs: { "aria-live": "polite" }, class: "main" });
  private readonly nav = h("nav", { attrs: { "aria-label": label.views }, class: "tabs" });
  private readonly filters = h("div", { class: "filters-host" });
  private index: TokensIndex | undefined;
  private timer: ReturnType<typeof setInterval> | undefined;

  readonly show = (): void => {
    void this.render(parseRoute(globalThis.location.hash));
  };

  /** Re-render the open view with fresh data, unless the reader is typing in it. */
  readonly refresh = (): void => {
    if (!this.main.contains(document.activeElement) || document.activeElement === document.body) this.show();
  };

  private setFilter(route: Route, key: string, value: string): void {
    const parameters = new URLSearchParams(route.parameters);
    if (value === "" || (key === "scope" && value === "all")) parameters.delete(key);
    else parameters.set(key, value);
    globalThis.location.hash = formatRoute({ ...route, parameters });
  }

  private drawNav(route: Route): void {
    const current = tabFor(route.view);
    const keep = new URLSearchParams([...route.parameters].filter(([key]) => !key.startsWith("t.")));
    this.nav.replaceChildren(...VIEWS.map((view) => h("a", { attrs: { "aria-current": view.id === current ? "page" : undefined, href: formatRoute({ arg: "", parameters: keep, view: view.id }) }, text: view.label })));
  }

  private async render(route: Route): Promise<void> {
    this.abort.abort();
    this.abort = new AbortController();
    const { signal } = this.abort;
    this.drawNav(route);
    const render = RENDERERS[route.view];
    this.main.setAttribute("aria-busy", "true");
    if (this.main.childElementCount === 0) this.main.replaceChildren(h("p", { class: "loading", text: `${label.loading} ${route.view}…` }));
    try {
      this.index ??= await loadIndex(signal);
      const index = this.index;
      this.filters.replaceChildren(filterBar(index, route.parameters, (key, value) => { this.setFilter(route, key, value); }));
      const view = await render(hashContext(), signal, route.arg);
      if (!signal.aborted) this.main.replaceChildren(view);
    } catch (error) {
      if (!signal.aborted) this.main.replaceChildren(h("p", { attrs: { role: "alert" }, class: "error", text: errorText(error) }));
    } finally {
      if (!signal.aborted) this.main.removeAttribute("aria-busy");
    }
  }

  connectedCallback(): void {
    this.replaceChildren(
      h("header", { class: "head" }, h("a", { attrs: { href: "/" }, class: "brand", text: label.brand }), h("h1", { text: label.title }), this.nav),
      this.filters,
      this.main,
    );
    globalThis.addEventListener("hashchange", this.show);
    this.timer = setInterval(this.refresh, REFRESH_MS);
    this.show();
  }

  disconnectedCallback(): void {
    globalThis.removeEventListener("hashchange", this.show);
    clearInterval(this.timer);
    this.abort.abort();
  }
}

export function defineUsage(): void {
  if (customElements.get("usage-app") === undefined) customElements.define("usage-app", UsageApp);
}
