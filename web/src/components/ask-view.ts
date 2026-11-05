/** The task drawer's question UI: compact cards that fit the area, an Edit link per card, a pager or phone stepper, one Send answers. */
import type { ActionSlot } from "@/components/drawer-sections";
import type { Tab } from "@/components/drawer-shell";
import type { TaskDetail } from "@/lib/schemas";
import type { Question } from "@/lib/schemas-common";

import {
  answersOf, type Ask, askOf, clampPager, effective, firstPage, fitCount, isLast, type Layout, layoutFor, nextPage, pageLabel,
  previousPage,
} from "@/components/ask-model";
import { h, must } from "@/lib/dom";

const FREE_TITLE = "Answer Claude";

export class AskPanel {
  #ask: Ask | null = null;
  #count = 0;
  readonly #edits = new Map<string, string>();
  readonly #editing = new Set<string>();
  #interactive = false;
  #live = false;
  #observer: null | ResizeObserver = null;
  #pager = firstPage;
  #root: HTMLElement | null = null;
  #total = 0;

  #draw(root: HTMLElement, ask: Ask, act: ActionSlot, redraw: () => void): void {
    const send = act(ask.kind === "spec" ? "spec-answers" : "send");
    this.#interactive = send !== null;
    const cards = ask.kind === "spec" ? ask.questions.map((question) => this.#card(root, question, redraw)) : [this.#freeCard(ask.text)];
    const nav = (kind: "back" | "next", label: string): HTMLButtonElement => h("button", { attrs: { "data-ask": kind, type: "button" }, class: "btn", on: { click: () => { this.#turn(kind); } }, text: label });
    root.replaceChildren(
      h("div", { class: "ask-grid" }, ...cards),
      h(
        "div",
        { class: "ask-foot" },
        h("div", { class: "ask-pager" }, nav("back", "Back"), h("span", { attrs: { "aria-live": "polite" }, class: "ask-page" }), nav("next", "Next")),
        h("div", { class: "ask-actions" }, send),
      ),
    );
  }

  #card(root: HTMLElement, question: Question, redraw: () => void): HTMLElement {
    const isEditing = this.#interactive && this.#editing.has(question.id);
    const value = effective(question, this.#edits);
    const field = h("textarea", {
      attrs: { "aria-label": `Answer to ${question.id}`, "data-keep": true, "data-qid": true, hidden: !isEditing, name: question.id, rows: 3 },
      on: {
        input: () => {
          this.#edits.set(question.id, field.value);
        },
      },
    });
    field.value = value;
    const toggle = (text: string, change: () => void): HTMLButtonElement => {
      return h("button", {
        attrs: { type: "button" },
        class: "link",
        on: {
          click: () => {
            change();
            redraw();
            if (this.#editing.has(question.id)) root.querySelector<HTMLTextAreaElement>(`textarea[name=${CSS.escape(question.id)}]`)?.focus();
          },
        },
        text,
      });
    };
    return h(
      "article",
      { class: "ask-card" },
      h("h4", { class: "ask-title", text: `${question.id} · ${question.title}` }),
      question.body !== "" && h("p", { class: "ask-body", text: question.body }),
      h("div", { class: "ask-answer" }, h("span", { class: "ask-label", text: this.#edits.has(question.id) || question.answer !== null ? "Your answer" : "Recommended" }), h("p", { attrs: { hidden: isEditing }, text: value }), field),
      this.#interactive && h(
        "div",
        { class: "ask-links" },
        toggle(isEditing ? "Done" : "Edit", () => {
          if (isEditing) this.#editing.delete(question.id);
          else this.#editing.add(question.id);
        }),
        isEditing && toggle("Use recommended", () => {
          this.#edits.set(question.id, question.recommendation);
        }),
      ),
    );
  }

  #freeCard(text: string): HTMLElement {
    return h(
      "article",
      { class: "ask-card" },
      h("h4", { class: "ask-title", text: FREE_TITLE }),
      h("p", { class: "ask-body", text }),
      this.#interactive && h("textarea", { attrs: { "aria-label": "Your answer to Claude", "data-keep": true, name: "ask-send", placeholder: "Your answer to Claude", rows: 4 } }),
    );
  }

  #turn(kind: "back" | "next"): void {
    this.#pager = kind === "next" ? nextPage(this.#pager, this.#count, this.#total) : previousPage(this.#pager);
    this.fit();
  }

  #paintPager(root: HTMLElement, mode: Layout["mode"], total: number, count: number): void {
    const { start } = this.#pager;
    this.#count = count;
    const label = pageLabel(mode, start, count, total);
    const isLastPage = isLast(start, count, total);
    must(root, ".ask-page").textContent = label;
    must<HTMLElement>(root, ".ask-pager").hidden = label === "";
    must<HTMLButtonElement>(root, "[data-ask=back]").disabled = this.#pager.back.length === 0;
    must<HTMLButtonElement>(root, "[data-ask=next]").disabled = isLastPage;
    must<HTMLElement>(root, ".ask-actions").hidden = mode === "step" && !isLastPage;
  }

  get interactive(): boolean {
    return this.#interactive;
  }

  reset(): void {
    this.#edits.clear();
    this.#editing.clear();
    this.#live = false;
    this.#pager = firstPage;
  }

  /** The tab to show: Questions the moment a question needs an answer, Activity once it is answered. */
  tabFor(detail: TaskDetail, current: Tab): Tab {
    const ask = askOf(detail);
    const isLive = ask !== null && (ask.kind === "free" || detail.card.actions.some((action) => action.id === "spec-answers"));
    const wasLive = this.#live;
    this.#live = isLive;
    if (isLive && !wasLive) return "questions";
    return current === "questions" && (ask === null || wasLive !== isLive) ? "activity" : current;
  }

  answers(): Record<string, string> {
    return this.#ask?.kind === "spec" ? answersOf(this.#ask.questions, this.#edits) : {};
  }

  build(detail: TaskDetail, act: ActionSlot): HTMLElement | null {
    this.#observer?.disconnect();
    const ask = askOf(detail);
    this.#ask = ask;
    this.#root = null;
    this.#interactive = false;
    if (ask === null) return null;
    const total = ask.kind === "spec" ? ask.questions.length : 1;
    this.#total = total;
    this.#pager = clampPager(this.#pager, total);
    const root = h("section", { attrs: { "aria-label": "Questions" }, class: "ask" });
    this.#root = root;
    const redraw = (): void => {
      this.#draw(root, ask, act, redraw);
      this.fit();
    };
    this.#draw(root, ask, act, redraw);
    if (typeof ResizeObserver !== "undefined") {
      this.#observer = new ResizeObserver(() => {
        this.fit();
      });
      this.#observer.observe(must(root, ".ask-grid"));
    }
    return root;
  }

  /** Show only the cards that fit the area from the pager's start, then label the pager. Run after every paint and resize. */
  fit(): void {
    const root = this.#root;
    if (root?.isConnected !== true) return;
    const grid = must<HTMLElement>(root, ".ask-grid");
    if (grid.clientWidth === 0) return;
    const layout = layoutFor(grid.clientWidth);
    const cards = [...grid.children] as HTMLElement[];
    const { start } = this.#pager;
    const isStepping = layout.mode === "step";
    if (isStepping) this.#paintPager(root, layout.mode, cards.length, 1);
    if (grid.clientHeight === 0) return;
    root.dataset.mode = layout.mode;
    grid.style.setProperty("--cols", String(Math.min(layout.cols, cards.length)));
    grid.style.setProperty("--ask-h", `${String(grid.clientHeight)}px`);
    for (const [index, card] of cards.entries()) { card.hidden = index < start; }
    const count = isStepping ? 1 : fitCount(cards.slice(start).map((card) => card.getBoundingClientRect().bottom), grid.getBoundingClientRect().bottom);
    for (const [index, card] of cards.entries()) { card.hidden = index < start || index >= start + count; }
    if (!isStepping) this.#paintPager(root, layout.mode, cards.length, count);
  }
}
