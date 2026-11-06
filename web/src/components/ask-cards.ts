/** Question markup: an editable answer field pre-filled with the draft, the saved answer or the recommendation. */
import type { Question } from "@/lib/schemas-common";

import { effective, sendingLabel } from "@/components/ask-model";
import { loader } from "@/components/feedback";
import { h } from "@/lib/dom";
import { inline } from "@/lib/markdown";

export type Status = { count: number; kind: "sending" } | { kind: "error"; message: string } | { kind: "idle" } | { kind: "waiting" };

export interface FieldHooks {
  onEnter?: () => void;
  onInput: (id: string, value: string) => void;
}

export const titleOf = (question: Question): string => `${question.id} · ${question.title}`;

/** The body as paragraphs (a blank line splits them) with `code` spans rendered. */
const bodyView = (text: string): HTMLElement =>
  h("div", { class: "ask-body" }, ...text.split(/\n\s*\n/v).map((paragraph) => h("p", {}, ...inline(paragraph.trim()))));

/** Title, body and the textarea, which grows with its text. Enter accepts, Shift+Enter is a newline. */
export function questionParts(question: Question, drafts: Readonly<Record<string, string>>, hooks: FieldHooks): HTMLElement[] {
  const value = effective(question, drafts);
  const field = h("textarea", {
    attrs: { "aria-label": `Answer to ${question.id}`, "data-keep": true, name: question.id, rows: 1 },
    on: {
      input: () => {
        hooks.onInput(question.id, field.value);
      },
      keydown: (event) => {
        if (event.key !== "Enter" || event.shiftKey || event.isComposing || hooks.onEnter === undefined) return;
        event.preventDefault();
        hooks.onEnter();
      },
    },
  });
  field.value = value;
  return [
    h("h4", { class: "ask-title", text: titleOf(question) }),
    question.body !== "" && bodyView(question.body),
    field,
  ].filter((node) => node !== false);
}

/** What the send is doing: a loader naming it, or the error with Retry (the answers stay). */
export function statusView(status: Status, retry: () => HTMLElement): HTMLElement {
  if (status.kind === "sending") return loader(sendingLabel(status.count));
  if (status.kind === "waiting") return loader("Sent. Waiting for the card to update…");
  return status.kind === "idle" ? h("p", { class: "ask-status" }) : h("div", { attrs: { role: "alert" }, class: "banner ask-status" }, h("span", { text: `${status.message} Your answers are kept.` }), retry());
}
