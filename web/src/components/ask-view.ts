/** The task drawer's question flow: one centered editable question at a time (Enter or swipe right = OK), an all-at-once view behind a bar icon, one automatic send. */
import type { ActionSlot } from "@/components/drawer-sections";
import type { Tab } from "@/components/drawer-shell";
import type { TaskDetail } from "@/lib/schemas";
import type { Question } from "@/lib/schemas-common";

import { type FieldHooks, type Status, statusView } from "@/components/ask-cards";
import { answersOf, askOf, firstOpen, nextOpen, NOT_WAITING, questionsOf, replyOf, waitingNote } from "@/components/ask-model";
import { allView, retryButton, type StepProps, stepView } from "@/components/ask-step";
import { type AskState, blankState, dropState, loadState, saveState, storeKey } from "@/components/ask-store";
import { iconButton, setIcon } from "@/components/icons";
import { h } from "@/lib/dom";
import { errorText } from "@/lib/http";

const ALL_LABEL = "All questions";
const ONE_LABEL = "One question at a time";

export interface AskHost {
  /** Runs after a successful send: refresh the card from the server. */
  done: (cardId: string) => Promise<void>;
  /** POST a plain Claude question's one answer as the card's send action; rejects with the server's message. */
  reply: (cardId: string, text: string) => Promise<void>;
  /** POST all answers once; rejects with the server's message. */
  send: (cardId: string, answers: Record<string, string>) => Promise<void>;
}

export class AskPanel {
  #questions: Question[] = [];
  #cardId = "";
  readonly #host: AskHost;
  /** A plain Claude question: one synthetic question, answered through the card's send action. */
  #free = false;
  #interactive = false;
  #key = "";
  #live = false;
  #mode: "all" | "step" = "step";
  /** Why the send action (spec-answers, or send for a plain question) cannot send now: null when it can, "" when it is disabled without a reason. */
  #note: null | string = null;
  #offered = false;
  #root: HTMLElement | null = null;
  #state: AskState = blankState(0);
  #status: Status = { kind: "idle" };
  readonly #switch: HTMLButtonElement;

  constructor(host: AskHost) {
    this.#host = host;
    this.#switch = iconButton("all", ALL_LABEL, { "data-ask-mode": true }, () => { this.#setMode(this.#mode === "step" ? "all" : "step"); });
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
    if (this.#mode === "step") setIcon(this.#switch, "all", ALL_LABEL);
    else setIcon(this.#switch, "one", ONE_LABEL);
    const view = this.#mode === "step"
      ? stepView(this.#props())
      : allView(this.#questions, this.#state.drafts, this.#hooks(), this.#busy, () => { void this.#submit(); });
    root.replaceChildren(
      view,
      statusView(this.#status, () => retryButton(() => { void this.#submit(); })),
    );
  }

  #props(): StepProps {
    let note = "";
    if (!this.#offered) note = NOT_WAITING;
    else if (this.#note !== null) note = waitingNote(this.#note);
    return {
      busy: this.#busy,
      drafts: this.#state.drafts,
      hooks: this.#hooks(),
      note,
      onBack: () => { this.#back(); },
      onOk: () => { this.#accept(); },
      questions: this.#questions,
      step: this.#state.step,
    };
  }

  #setMode(mode: "all" | "step"): void {
    this.#mode = mode;
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

  #back(): void {
    if (this.#state.step === 0 || this.#busy) return;
    this.#state = { ...this.#state, step: this.#state.step - 1 };
    this.#save();
    this.#paint();
    this.focus();
  }

  /** OK: on to the next open question; after the last one the answers go out at once, or wait for the action. */
  #accept(): void {
    if (this.#busy) return;
    const { step } = this.#state;
    const next = nextOpen(this.#questions, step);
    if (next !== -1) {
      this.#state = { ...this.#state, step: next };
      this.#save();
      this.#paint();
      this.focus();
      return;
    }
    this.#state = { ...this.#state, queued: this.#offered && this.#note !== null };
    this.#save();
    if (this.#offered && this.#note === null) void this.#submit();
    else this.#paint();
  }

  /** One POST with every answer; the loader names it, an error keeps the answers and offers Retry. */
  async #submit(): Promise<void> {
    const answers = answersOf(this.#questions, this.#state.drafts);
    const count = Object.keys(answers).length;
    this.#state = { ...this.#state, queued: false };
    this.#save();
    if (count === 0) {
      this.#status = { kind: "error", message: "Write at least one answer first." };
      this.#paint();
      return;
    }
    const cardId = this.#cardId;
    this.#status = { count, kind: "sending" };
    this.#paint();
    try {
      if (this.#free) await this.#host.reply(cardId, replyOf(this.#questions, answers));
      else await this.#host.send(cardId, answers);
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

  /** The top-bar icon that flips between one question at a time and all of them; null when there is nothing to switch. */
  get switcher(): HTMLElement | null {
    const least = this.#free ? 2 : 1;
    return this.#questions.length >= least ? this.#switch : null;
  }

  get interactive(): boolean {
    return this.#interactive;
  }

  reset(): void {
    this.#key = "";
    this.#live = false;
    this.#mode = "step";
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
    this.#free = ask?.kind === "free";
    this.#questions = ask === null ? [] : questionsOf(ask);
    this.#root = null;
    this.#interactive = false;
    if (ask === null) return null;
    const root = h("section", { attrs: { "aria-label": "Questions" }, class: "ask" });
    this.#root = root;
    // The server's spec-answers (or send) action only gates the send: its own button is never drawn (answers send themselves).
    const gate = this.#free ? "send" : "spec-answers";
    const action = detail.card.actions.find((candidate) => candidate.id === gate);
    act(gate);
    this.#interactive = true;
    this.#offered = action !== undefined;
    this.#note = action === undefined || action.enabled ? null : (action.reason ?? "");
    this.#cardId = detail.card.id;
    const key = storeKey(this.#free ? `${this.#cardId}.free` : this.#cardId, this.#questions);
    if (key !== this.#key) {
      this.#key = key;
      const saved = loadState(key) ?? blankState(firstOpen(this.#questions));
      this.#state = { ...saved, step: Math.min(saved.step, this.#questions.length - 1) };
    }
    this.#paint();
    if (this.#offered && this.#note === null && this.#state.queued && !this.#busy) void this.#submit();
    return root;
  }
}
