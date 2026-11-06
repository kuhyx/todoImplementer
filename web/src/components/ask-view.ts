/** The task drawer's question flow: one editable question at a time (Enter or swipe right accepts), an all-at-once tab, one automatic send. */
import type { ActionSlot } from "@/components/drawer-sections";
import type { Tab } from "@/components/drawer-shell";
import type { TaskDetail } from "@/lib/schemas";
import type { Question } from "@/lib/schemas-common";

import { type FieldHooks, questionParts, readCard, type Status, statusView } from "@/components/ask-cards";
import { answersOf, askOf, firstOpen, progressLabel } from "@/components/ask-model";
import { type AskState, blankState, dropState, loadState, saveState, storeKey } from "@/components/ask-store";
import { attachSwipe } from "@/components/ask-swipe";
import { h } from "@/lib/dom";
import { errorText } from "@/lib/http";

const FREE_TITLE = "Answer Claude";

export interface AskHost {
  /** Runs after a successful send: refresh the card from the server. */
  done: (cardId: string) => Promise<void>;
  /** POST all answers once; rejects with the server's message. */
  send: (cardId: string, answers: Record<string, string>) => Promise<void>;
}

export class AskPanel {
  #questions: Question[] = [];
  #cardId = "";
  readonly #host: AskHost;
  #interactive = false;
  #key = "";
  #live = false;
  #reason = "";
  #root: HTMLElement | null = null;
  #state: AskState = blankState(0);
  #status: Status = { kind: "idle" };

  constructor(host: AskHost) {
    this.#host = host;
  }

  get #busy(): boolean {
    return this.#status.kind === "sending" || this.#status.kind === "waiting";
  }

  #save(): void {
    saveState(this.#key, this.#state);
  }

  #paint(): void {
    const root = this.#root;
    if (root === null) return;
    const questions = this.#questions;
    if (!this.#interactive) {
      root.replaceChildren(...(this.#reason === "" ? [] : [h("p", { class: "ask-reason", text: this.#reason })]), h("div", { class: "ask-list" }, ...questions.map((question) => readCard(question, this.#state.drafts))));
      return;
    }
    const mode = (kind: AskState["mode"], text: string): HTMLButtonElement =>
      h("button", { attrs: { "aria-pressed": this.#state.mode === kind, "data-mode": kind, type: "button" }, class: "dtab", on: { click: () => { this.#setMode(kind); } }, text });
    root.replaceChildren(
      h("div", { attrs: { "aria-label": "Question view", role: "group" }, class: "ask-modes" }, mode("step", "One by one"), mode("all", "All questions")),
      this.#state.mode === "step" ? this.#stepView(questions) : this.#allView(questions),
      statusView(this.#status, () => this.#button("Retry", { "data-ask": "retry" }, () => { void this.#submit(); })),
    );
  }

  #setMode(mode: AskState["mode"]): void {
    this.#state = { ...this.#state, mode };
    this.#save();
    this.#paint();
    this.focus();
  }

  #hooks(): FieldHooks {
    return {
      onInput: (id, value) => {
        this.#state = { ...this.#state, drafts: { ...this.#state.drafts, [id]: value } };
        this.#save();
      },
    };
  }

  #button(text: string, attributes: Record<string, string>, click: () => void, extra = ""): HTMLButtonElement {
    return h("button", { attrs: { ...attributes, "aria-disabled": this.#busy, type: "button" }, class: `btn${extra}`, on: { click: () => { if (!this.#busy) click(); } }, text });
  }

  #stepView(questions: Question[]): HTMLElement {
    const { step } = this.#state;
    const isLast = step === questions.length - 1;
    const view = h(
      "section",
      { attrs: { "aria-label": `Question ${progressLabel(step, questions.length)}` }, class: "ask-card ask-step" },
      h("span", { attrs: { "aria-live": "polite" }, class: "ask-page", text: progressLabel(step, questions.length) }),
      ...questions.slice(step, step + 1).flatMap((shown) => questionParts(shown, this.#state.drafts, { ...this.#hooks(), onEnter: () => { this.#accept(); } })),
      h(
        "div",
        { class: "ask-foot" },
        this.#button("Back", { "data-ask": "back" }, () => { this.#back(); }),
        this.#button(isLast ? `Accept and send ${String(questions.length)}` : "Accept", { "data-ask": "accept" }, () => { this.#accept(); }, " primary"),
      ),
    );
    attachSwipe(view, (direction) => {
      if (this.#busy) return;
      if (direction === "next") this.#accept();
      else this.#back();
    });
    return view;
  }

  #allView(questions: Question[]): HTMLElement {
    return h(
      "div",
      { class: "ask-all" },
      h("div", { class: "ask-list" }, ...questions.map((question) => h("article", { class: "ask-card" }, ...questionParts(question, this.#state.drafts, this.#hooks())))),
      h("div", { class: "ask-foot" }, this.#button(`Accept all ${String(questions.length)}`, { "data-ask": "accept-all" }, () => { void this.#submit(); }, " primary")),
    );
  }

  #back(): void {
    if (this.#state.step === 0) return;
    this.#state = { ...this.#state, step: this.#state.step - 1 };
    this.#save();
    this.#paint();
    this.focus();
  }

  #accept(): void {
    if (this.#busy) return;
    const { accepted, step } = this.#state;
    const ids = this.#questions.slice(step, step + 1).map((question) => question.id);
    const next = Math.min(step + 1, this.#questions.length - 1);
    this.#state = { ...this.#state, accepted: [...accepted.filter((id) => !ids.includes(id)), ...ids], step: next };
    this.#save();
    if (step === this.#questions.length - 1) {
      void this.#submit();
      return;
    }
    this.#paint();
    this.focus();
  }

  /** One POST with every answer; the loader names it, an error keeps the answers and offers Retry. */
  async #submit(): Promise<void> {
    const answers = answersOf(this.#questions, this.#state.drafts);
    const count = Object.keys(answers).length;
    if (count === 0) {
      this.#status = { kind: "error", message: "Write at least one answer first." };
      this.#paint();
      return;
    }
    const cardId = this.#cardId;
    this.#status = { count, kind: "sending" };
    this.#paint();
    try {
      await this.#host.send(cardId, answers);
    } catch (error) {
      this.#status = { kind: "error", message: errorText(error) };
      this.#paint();
      return;
    }
    dropState(this.#key);
    this.#state = blankState(0);
    this.#key = "";
    this.#status = { kind: "waiting" };
    this.#paint();
    await this.#host.done(cardId);
    this.#status = { kind: "idle" };
    this.#paint();
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

  get interactive(): boolean {
    return this.#interactive;
  }

  reset(): void {
    this.#key = "";
    this.#live = false;
    this.#status = { kind: "idle" };
  }

  /** Put the cursor in the current answer so typing or Enter works at once. */
  focus(): void {
    if (this.#root?.isConnected !== true || this.#root.closest("[hidden]") !== null) return;
    this.#root.querySelector<HTMLTextAreaElement>("textarea")?.focus();
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

  build(detail: TaskDetail, act: ActionSlot): HTMLElement | null {
    const ask = askOf(detail);
    this.#questions = ask?.kind === "spec" ? ask.questions : [];
    this.#root = null;
    this.#interactive = false;
    if (ask === null) return null;
    const root = h("section", { attrs: { "aria-label": "Questions" }, class: "ask" });
    this.#root = root;
    if (ask.kind === "free") {
      const send = act("send");
      this.#interactive = send !== null;
      root.append(this.#freeCard(ask.text), h("div", { class: "ask-foot" }, send));
      return root;
    }
    // The server's spec-answers action only gates the flow: its own button is never drawn (answers send themselves).
    const action = detail.card.actions.find((candidate) => candidate.id === "spec-answers");
    act("spec-answers");
    this.#interactive = action?.enabled === true;
    this.#reason = action?.enabled === false ? (action.reason ?? "") : "";
    this.#cardId = detail.card.id;
    const key = storeKey(this.#cardId, ask.questions);
    if (key !== this.#key) {
      this.#key = key;
      const fresh = blankState(firstOpen(ask.questions));
      const saved = loadState(key) ?? fresh;
      this.#state = { ...saved, step: Math.min(saved.step, ask.questions.length - 1) };
    }
    this.#paint();
    return root;
  }
}
