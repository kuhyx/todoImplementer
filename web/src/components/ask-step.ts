/** The two views of the question flow: one centered question with its answer and two icons, or every question at once. */
import type { Question } from "@/lib/schemas-common";

import { type FieldHooks, questionParts } from "@/components/ask-cards";
import { attachSwipe } from "@/components/ask-swipe";
import { iconButton, type IconName } from "@/components/icons";
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

/** The one text button left: Retry, which only exists once the send has stopped. */
export function retryButton(click: () => void): HTMLButtonElement {
  return h("button", { attrs: { "data-ask": "retry", type: "button" }, class: "btn", on: { click }, text: "Retry" });
}

/** An icon-only button that does nothing while a send is running. */
const iconAction = (name: IconName, label: string, attributes: Record<string, string>, isBusy: boolean, click: () => void, extra = ""): HTMLButtonElement =>
  iconButton(name, label, { ...attributes, "aria-disabled": isBusy }, () => { if (!isBusy) click(); }, extra);

/** One question, centered: title, body, answer; Back (left) and OK (right) under it; why it cannot send yet in small print. */
export function stepView(props: StepProps): HTMLElement {
  const { busy, questions, step } = props;
  const shown = questions.slice(step, step + 1);
  const view = h(
    "section",
    { attrs: { "aria-label": `Question ${String(step + 1)}` }, class: "ask-card ask-step" },
    h(
      "div",
      { class: "ask-center" },
      ...shown.flatMap((question) => questionParts(question, props.drafts, { ...props.hooks, onEnter: props.onOk })),
      h(
        "div",
        { class: "ask-nav" },
        iconAction("back", "Back", { "data-ask": "back" }, busy, props.onBack, "ask-back"),
        iconAction("check", "OK", { "data-ask": "accept" }, busy, props.onOk, "primary ask-ok"),
      ),
      props.note !== "" && h("p", { class: "ask-reason", text: props.note }),
    ),
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
    h("div", { class: "ask-nav" }, iconAction("check", `OK, send all ${String(questions.length)}`, { "data-ask": "accept-all" }, isBusy, send, "primary ask-ok")),
  );
}
