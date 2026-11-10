/** <ti-app>: owns the polling loops, the URL hash and the wiring between usage strip, toolbar, board and drawer. */
import { renderBoard } from "@/components/board-columns";
import { defineDrawer, TiDrawer } from "@/components/drawer";
import { loader } from "@/components/feedback";
import { defineMerges } from "@/components/merge-strip";
import { createToolbar, type Toolbar } from "@/components/toolbar";
import { renderUsage } from "@/components/usage-strip";
import { buildView } from "@/lib/board-model";
import { pageBuild } from "@/lib/boot";
import { h, must } from "@/lib/dom";
import { DEFAULT_STATE, formatHash, parseHash, type ViewState } from "@/lib/hash-state";
import { errorText, getJson } from "@/lib/http";
import { poll } from "@/lib/poller";
import { routes } from "@/lib/routes";
import { type Board, board as boardSchema, type Usage, usage as usageSchema } from "@/lib/schemas";

export const BOARD_POLL_MS = 3000;
export const USAGE_POLL_MS = 10_000;
const nowSeconds = (): number => Math.floor(Date.now() / 1000);

export class TiApp extends HTMLElement {
  #board: Board | null = null;
  #boardError: null | string = null;
  #boardHost = h("main", { attrs: { "aria-live": "off" }, class: "board-host" }, loader(`Loading the board from ${routes.board}…`));
  readonly #drawer = new TiDrawer();
  #signature = "";
  #state: ViewState = DEFAULT_STATE;
  #stops: (() => void)[] = [];
  readonly #toolbar: Toolbar = createToolbar({
    onChange: (patch) => {
      this.#setState({ ...this.#state, ...patch }, "replace");
    },
  });
  #usage: null | Usage = null;
  #usageError: null | string = null;
  #usageHost = h("header", { class: "usage-host" });

  readonly #onHash = (): void => {
    this.#state = parseHash(location.hash);
    this.#paintBoard(true);
    this.#syncDrawer(null);
  };

  #setState(next: ViewState, mode: "push" | "replace", opener: HTMLElement | null = null): void {
    this.#state = next;
    const hash = formatHash(next);
    const url = `${location.pathname}${location.search}${hash}`;
    if (mode === "push") history.pushState(null, "", url);
    else history.replaceState(null, "", url);
    this.#paintBoard(true);
    this.#syncDrawer(opener);
  }

  #syncDrawer(opener: HTMLElement | null): void {
    const drawer = this.#drawer;
    const { task } = this.#state;
    if (task === null) {
      if (!drawer.hidden) drawer.close(false);
    } else if (drawer.hidden || drawer.dataset.task !== task) {
      drawer.dataset.task = task;
      drawer.open(task, opener);
    }
  }

  async #loadBoard(): Promise<void> {
    try {
      const board = await getJson(routes.board, boardSchema);
      this.#boardError = null;
      this.#board = board;
    } catch (error) {
      this.#boardError = errorText(error);
    }
    this.#paintUsage();
    this.#paintBoard(false);
    if (this.#drawer.hidden) this.#syncDrawer(null);
  }

  async #loadUsage(): Promise<void> {
    try {
      this.#usage = await getJson(routes.usage, usageSchema);
      this.#usageError = null;
    } catch (error) {
      this.#usageError = `Usage numbers unavailable: ${errorText(error)}`;
    }
    this.#paintUsage();
  }

  #staleReason(): null | string {
    if (this.#boardError !== null) return `Board not refreshed: ${this.#boardError}`;
    const reported = this.#board?.error;
    return reported ? `Todo notes unavailable (${reported.code}): ${reported.message}. These cards are the last known ones.` : null;
  }

  #paintUsage(): void {
    const stale = this.#staleReason();
    this.#boardHost.toggleAttribute("data-stale", stale !== null);
    this.#usageHost.replaceChildren(renderUsage(this.#usage, this.#board, stale ?? this.#usageError, pageBuild(), nowSeconds(), () => void this.#loadBoard()));
  }

  #paintBoard(isForced: boolean): void {
    const board = this.#board;
    if (board === null) return;
    this.#toolbar.el.hidden = false;
    this.#toolbar.update(board, this.#state);
    const now = nowSeconds();
    const signature = JSON.stringify([board, this.#state.q, this.#state.repo, this.#state.sort, this.#state.col, Math.floor(now / 60)]);
    if (!isForced && signature === this.#signature) return;
    this.#signature = signature;
    const scrolls = this.#bodies().map((body) => body.scrollTop);
    const focused = document.querySelector<HTMLElement>(":focus")?.dataset.id;
    this.#boardHost.replaceChildren(
      renderBoard(buildView(board, this.#state), this.#state, now, {
        onColumn: (col) => { this.#setState({ ...this.#state, col }, "replace"); },
        onOpen: (id) => { this.#setState({ ...this.#state, task: id }, "push", this.#boardHost.querySelector<HTMLElement>(`[data-id="${CSS.escape(id)}"]`)); },
      }),
    );
    for (const [index, body] of this.#bodies().entries()) body.scrollTop = scrolls[index] ?? 0;
    if (focused) this.#boardHost.querySelector<HTMLElement>(`[data-id="${CSS.escape(focused)}"]`)?.focus();
  }

  #bodies(): HTMLElement[] {
    return [...this.#boardHost.querySelectorAll<HTMLElement>(".col")].map((col) => must(col, ".col-body"));
  }

  connectedCallback(): void {
    this.#state = parseHash(location.hash);
    this.#drawer.hidden = true;
    this.#drawer.addEventListener("drawer-close", () => {
      this.#setState({ ...this.#state, task: null }, "replace");
    });
    this.#drawer.addEventListener("task-changed", () => void this.#loadBoard());
    this.append(this.#usageHost, this.#toolbar.el, document.createElement("ti-merges"), this.#boardHost, this.#drawer);
    this.#paintUsage();
    this.#toolbar.el.hidden = true;
    addEventListener("hashchange", this.#onHash);
    this.#stops = [poll(() => this.#loadBoard(), BOARD_POLL_MS), poll(() => this.#loadUsage(), USAGE_POLL_MS)];
  }

  disconnectedCallback(): void {
    removeEventListener("hashchange", this.#onHash);
    for (const stop of this.#stops) stop();
    this.#stops = [];
  }
}

export function defineApp(): void {
  defineDrawer();
  defineMerges();
  if (!customElements.get("ti-app")) customElements.define("ti-app", TiApp);
}
