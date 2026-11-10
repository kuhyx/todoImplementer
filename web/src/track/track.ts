/** <ti-track>: the live tracking view of one umbrella run. Fetches at once, refetches on every SSE event and every 5 s. */
import type { Track } from "@/lib/schemas-track";

import { loader } from "@/components/feedback";
import { icon, iconButton } from "@/components/icons";
import { h } from "@/lib/dom";
import { errorText, getJson } from "@/lib/http";
import { openLive } from "@/lib/live-feed";
import { poll } from "@/lib/poller";
import { routes } from "@/lib/routes";
import { track as trackSchema } from "@/lib/schemas-track";
import { renderHead } from "@/track/track-head";
import { renderIssues } from "@/track/track-issues";
import { type Expand, renderKids } from "@/track/track-kids";
import { renderRounds } from "@/track/track-rounds";

export const TRACK_POLL_MS = 5000;
export const DEBOUNCE_MS = 150;
const BACK_LABEL = "Back to the board";
const nowSeconds = (): number => Math.floor(Date.now() / 1000);
/** A bad frame or a connection change needs no handling here: the next event or the 5 s poll refetches. */
const noop = (): void => undefined;

export class TiTrack extends HTMLElement {
  #applied = 0;
  #data: null | Track = null;
  #error: null | string = null;
  #id: null | string = null;
  readonly #open = new Set<string>();
  #pending: ReturnType<typeof setTimeout> | undefined;
  #seq = 0;
  #stops: (() => void)[] = [];

  readonly #expand: Expand = {
    has: (key) => this.#open.has(key),
    toggle: (key) => {
      if (!this.#open.delete(key)) this.#open.add(key);
      this.#paint();
    },
  };

  #stop(): void {
    clearTimeout(this.#pending);
    this.#pending = undefined;
    for (const stop of this.#stops) stop();
    this.#stops = [];
  }

  /** An event burst (a worker prints a line a second) becomes one fetch. */
  #soon(id: string): void {
    if (this.#pending !== undefined) return;
    this.#pending = setTimeout(() => {
      this.#pending = undefined;
      void this.#load(id);
    }, DEBOUNCE_MS);
  }

  async #load(id: string): Promise<void> {
    const mine = ++this.#seq;
    try {
      const data = await getJson(routes.umbrella(id), trackSchema);
      if (mine < this.#applied || id !== this.#id) return;
      this.#applied = mine;
      this.#data = data;
      this.#error = null;
    } catch (error) {
      if (mine < this.#applied || id !== this.#id) return;
      this.#error = errorText(error);
    }
    this.#paint();
  }

  #top(id: string): HTMLElement {
    const isStale = this.#error !== null;
    return h(
      "div",
      { class: "t-top" },
      iconButton("back", BACK_LABEL, { "data-close": "" }, () => {
        this.dispatchEvent(new CustomEvent("track-close"));
      }),
      h("h2", { class: "t-title", text: this.#data?.title ?? id }),
      isStale && h("span", { attrs: { "aria-label": this.#error, "data-stale-mark": "", role: "img", title: this.#error }, class: "t-stale" }, icon("offline")),
    );
  }

  #body(id: string): HTMLElement[] {
    const data = this.#data;
    if (data === null) return [this.#error === null ? loader(`Loading the umbrella run from ${routes.umbrella(id)}…`) : h("p", { attrs: { role: "alert" }, class: "banner", text: this.#error })];
    return [
      renderHead(data, nowSeconds()),
      data.rounds.length > 0 && renderRounds(data.rounds),
      renderKids(data.kids, id, nowSeconds(), this.#expand),
      data.issues.total > 0 && renderIssues(data.issues, id, this.#expand),
    ].filter((part): part is HTMLElement => part !== false);
  }

  #paint(): void {
    const id = this.#id;
    if (id === null) {
      this.replaceChildren();
      return;
    }
    const scroll = this.scrollTop;
    const strip = this.querySelector<HTMLElement>(".t-strip")?.scrollLeft ?? 0;
    this.toggleAttribute("data-stale", this.#error !== null && this.#data !== null);
    this.replaceChildren(this.#top(id), ...this.#body(id));
    this.scrollTop = scroll;
    const fresh = this.querySelector<HTMLElement>(".t-strip");
    if (fresh !== null) fresh.scrollLeft = strip;
  }

  /** Show (or switch to) the run of umbrella `id`; null stops everything. */
  show(id: null | string): void {
    if (id === this.#id) return;
    this.#stop();
    this.#id = id;
    this.#data = null;
    this.#error = null;
    this.#open.clear();
    this.#paint();
    if (id === null) return;
    this.#stops = [
      poll(() => this.#load(id), TRACK_POLL_MS),
      openLive(id, {
        onBad: noop,
        onEvent: () => {
          this.#soon(id);
        },
        onState: noop,
      }),
    ];
  }

  disconnectedCallback(): void {
    this.#stop();
    this.#id = null;
  }
}

export function defineTrack(): void {
  if (!customElements.get("ti-track")) customElements.define("ti-track", TiTrack);
}
