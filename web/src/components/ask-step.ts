/** The two views of the question flow: one big question with its prefilled box and OK, or every question at once. */
import type { Question } from "@/lib/schemas-common";

import { type FieldHooks, questionParts } from "@/components/ask-cards";
import { progressLabel } from "@/components/ask-model";
import { attachSwipe } from "@/components/ask-swipe";
import { h } from "@/lib/dom";

export interface StepProps {
  busy: boolean;
  drafts: Readonly<Record<string, string>>;
  hooks: FieldHooks;
  note: string;
  onBack: () => void;
  onOk: () => void;
  questions: readonly Question[];
  step: number;
}

export function actionButton(text: string, attributes: Record<string, string>, isBusy: boolean, click: () => void, extra = "btn"): HTMLButtonElement {
  return h("button", { attrs: { ...attributes, "aria-disabled": isBusy, type: "button" }, class: extra, on: { click: () => { if (!isBusy) click(); } }, text });
}

/** One question: progress, title, body, box, one primary OK, a small Back link, then why it cannot send yet. */
export function stepView(props: StepProps): HTMLElement {
  const { busy, questions, step } = props;
  const view = h(
    "section",
    { attrs: { "aria-label": `Question ${progressLabel(step, questions.length)}` }, class: "ask-card ask-step" },
    h("span", { attrs: { "aria-live": "polite" }, class: "ask-page", text: progressLabel(step, questions.length) }),
    ...questions.slice(step, step + 1).flatMap((shown) => questionParts(shown, props.drafts, { ...props.hooks, onEnter: props.onOk })),
    actionButton("OK", { "data-ask": "accept" }, busy, props.onOk, "btn primary ask-ok"),
    actionButton("Back", { "data-ask": "back" }, busy, props.onBack, "ask-back"),
    props.note !== "" && h("p", { class: "ask-reason", text: props.note }),
  );
  attachSwipe(view, (direction) => {
    if (busy) return;
    if (direction === "next") props.onOk();
    else props.onBack();
  });
  return view;
}

export function allView(questions: readonly Question[], drafts: Readonly<Record<string, string>>, hooks: FieldHooks, isBusy: boolean, send: () => void): HTMLElement {
  return h(
    "div",
    { class: "ask-all" },
    h("div", { class: "ask-list" }, ...questions.map((question) => h("article", { class: "ask-card" }, ...questionParts(question, drafts, hooks)))),
    h("div", { class: "ask-foot" }, actionButton(`OK, send all ${String(questions.length)}`, { "data-ask": "accept-all" }, isBusy, send, "btn primary")),
  );
}
