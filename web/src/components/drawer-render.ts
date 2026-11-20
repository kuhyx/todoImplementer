import type { AskPanel } from "@/components/ask-view";
import type { Tab } from "@/components/drawer-shell";
import type { TaskDetail } from "@/lib/schemas";
import type { ActionId } from "@/lib/schemas-common";

/** Fill the drawer's slots and panels from one task detail. Every button comes from the card's actions[]. */
import { type BarHost, type BarState, pendingLoader, renderAction } from "@/components/action-bar";
import { renderAskItems } from "@/components/ask-items";
import {
  renderChecks, renderDetails, renderDiff, renderHead, renderLesson, renderLiveCheck, renderNeeds, renderPlan,
} from "@/components/drawer-sections";
import { h, must } from "@/lib/dom";

const present = (node: HTMLElement | null): HTMLElement[] => (node === null ? [] : [node]);

export function paintDetail(root: HTMLElement, detail: TaskDetail, host: BarHost, bar: BarState, ask: AskPanel): void {
  const slot = (name: string): HTMLElement => must(root, `[data-slot="${name}"]`);
  const used = new Set<ActionId>();
  const act = (id: ActionId): HTMLElement | null => {
    const action = detail.card.actions.find((candidate) => candidate.id === id);
    if (action === undefined) return null;
    used.add(id);
    return renderAction(action, host, detail.card.id);
  };
  const questions = ask.build(detail, act);
  const lesson = renderLesson(detail, act);
  const needs = renderNeeds(detail, ask.interactive, act);
  const send = used.has("send") ? null : act("send");
  const rest = detail.card.actions
    .filter((action) => !used.has(action.id))
    .map((action) => renderAction(action, host, detail.card.id));
  const pending = detail.card.actions.find((action) => action.id === bar.pending);
  slot("head").replaceChildren(renderHead(detail));
  slot("needs").replaceChildren(...present(needs));
  slot("asks").replaceChildren(...present(renderAskItems(detail)));
  slot("actions").replaceChildren(h("div", { class: "actions" }, ...rest));
  slot("pending").replaceChildren(...present(pendingLoader(pending, detail.card.id, bar)));
  slot("questions").replaceChildren(...present(questions));
  slot("mode").replaceChildren(...present(ask.switcher));
  slot("lesson").replaceChildren(...present(lesson));
  slot("send-action").replaceChildren(...present(send));
  slot("send").hidden = send === null;
  const panels: Record<Exclude<Tab, "activity" | "questions">, HTMLElement> = {
    checks: renderChecks(detail),
    details: renderDetails(detail),
    diff: renderDiff(detail),
    live: renderLiveCheck(detail),
    plan: renderPlan(detail),
  };
  for (const [tab, node] of Object.entries(panels)) must(root, `[data-panel="${tab}"]`).replaceChildren(node);
}
