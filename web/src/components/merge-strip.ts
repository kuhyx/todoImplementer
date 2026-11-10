import type { MergeAction, MergeActionId, Suggestion } from "@/lib/schemas-merge";

/**
 * <ti-merges>: one card per suggested group of similar notes, above the board. Icon-only: the header is a glyph,
 * the member count; only the members' own titles (user content) are words. Merge and dismiss come only
 * from the server's actions (a disabled merge keeps its reason as its tooltip). Nothing merges without the click.
 */
import { showToast, SLOW_MS } from "@/components/feedback";
import { icon, iconButton } from "@/components/icons";
import { csrfToken } from "@/lib/boot";
import { h } from "@/lib/dom";
import { errorText } from "@/lib/http";
import { getMerges, postMerge } from "@/lib/merge-api";
import { poll } from "@/lib/poller";

export const MERGE_POLL_MS = 5000;
const WAIT_NAME: Record<MergeActionId, string> = { dismiss: "Dismissing", merge: "Merging" };

interface Flight {
  action: MergeActionId;
  slow: boolean;
}

interface Paint {
  act: (action: MergeActionId) => void;
  failed: boolean;
  flight: Flight | undefined;
}

function button(action: MergeAction, paint: Paint): HTMLButtonElement {
  const isBusy = paint.flight?.action === action.id;
  const element = iconButton(
    action.id === "merge" ? "merge" : "close",
    action.label,
    { "aria-busy": isBusy, "data-action": action.id, disabled: !action.enabled || paint.flight !== undefined },
    () => {
      paint.act(action.id);
    },
  );
  if (!action.enabled && action.reason !== null) element.title = action.reason;
  return element;
}

export function renderSuggestion(suggestion: Suggestion, paint: Paint): HTMLElement {
  const wait = paint.flight?.slow === true ? WAIT_NAME[paint.flight.action] : null;
  return h(
    "article",
    { attrs: { "data-busy": paint.flight !== undefined, "data-error": paint.failed, "data-id": suggestion.id }, class: "merge" },
    h(
      "header",
      { class: "merge-head" },
      h("span", { attrs: { "aria-hidden": "true" }, class: "merge-glyph" }, icon("merge")),
      h("span", { class: "count merge-count", text: String(suggestion.members.length) }),
      h("span", { class: "merge-actions" }, ...suggestion.actions.map((action) => button(action, paint))),
    ),
    wait !== null && h("span", { attrs: { "aria-label": wait, role: "status" }, class: "spinner" }),
    h(
      "ul",
      { class: "merge-members" },
      ...suggestion.members.map((member) =>
        h("li", { class: "merge-member" }, h("span", { class: "merge-member-title", text: member.title }), h("span", { class: "merge-member-repo", text: member.repo })),
      ),
    ),
  );
}

export class TiMerges extends HTMLElement {
  readonly #failed = new Set<string>();
  readonly #flights = new Map<string, Flight>();
  #items: Suggestion[] = [];
  #signature = "";
  #stop: (() => void) | null = null;

  #paint(): void {
    const signature = JSON.stringify([this.#items, [...this.#flights], [...this.#failed]]);
    if (signature === this.#signature) return;
    this.#signature = signature;
    this.hidden = this.#items.length === 0;
    this.replaceChildren(
      ...this.#items.map((suggestion) => {
        return renderSuggestion(suggestion, {
          act: (action) => void this.#click(suggestion.id, action),
          failed: this.#failed.has(suggestion.id),
          flight: this.#flights.get(suggestion.id),
        });
      },
      ),
    );
  }

  async #click(group: string, action: MergeActionId): Promise<void> {
    const csrf = csrfToken();
    this.#failed.delete(group);
    if (csrf === null) {
      this.#failed.add(group);
      this.#paint();
      return;
    }
    const flight: Flight = { action, slow: false };
    this.#flights.set(group, flight);
    this.#paint();
    const timer = setTimeout(() => {
      flight.slow = true;
      this.#signature = "";
      this.#paint();
    }, SLOW_MS);
    try {
      this.#items = await postMerge(group, action, csrf);
    } catch (error) {
      this.#failed.add(group);
      showToast(errorText(error), "error");
    }
    clearTimeout(timer);
    this.#flights.delete(group);
    this.#paint();
  }

  async #load(): Promise<void> {
    // A failed poll is not news: the last list stays, the board's own banner reports a dead server.
    try {
      this.#items = await getMerges();
    } catch {
      // the last list stays
    }
    this.#paint();
  }

  connectedCallback(): void {
    this.classList.add("merges");
    this.hidden = true;
    this.#stop = poll(() => this.#load(), MERGE_POLL_MS);
  }

  disconnectedCallback(): void {
    this.#stop?.();
    this.#stop = null;
  }
}

export function defineMerges(): void {
  if (!customElements.get("ti-merges")) customElements.define("ti-merges", TiMerges);
}
