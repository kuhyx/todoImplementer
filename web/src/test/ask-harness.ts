/** Shared helpers for the AskPanel tests: a fake host, a mount with the card actions, and DOM shortcuts. */
import { afterEach, beforeEach, vi } from "vitest";

import type { Action } from "@/lib/schemas-common";

import { AskPanel } from "@/components/ask-view";
import { ASK_ID, askDetail } from "@/test/fixture-ask";

export const q = <T extends HTMLElement = HTMLElement>(selector: string): T => {
  const found = document.querySelector<T>(selector);
  if (found === null) throw new Error(selector);
  return found;
};
export const field = (): HTMLTextAreaElement => q<HTMLTextAreaElement>("textarea");
export const page = (): string => q(".ask-page").textContent;
export const type = (value: string): void => {
  field().value = value;
  field().dispatchEvent(new Event("input"));
};
export const key = (name: string, init: KeyboardEventInit = {}): KeyboardEvent => {
  const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: name, ...init });
  field().dispatchEvent(event);
  return event;
};
export const swipe = (dx: number): void => {
  q(".ask-step").dispatchEvent(Object.assign(new Event("pointerdown", { bubbles: true }), { clientX: 200, clientY: 100, pointerType: "touch" }));
  q(".ask-step").dispatchEvent(Object.assign(new Event("pointerup", { bubbles: true }), { clientX: 200 + dx, clientY: 100, pointerType: "touch" }));
};
export const flush = async (): Promise<void> => {
  await vi.advanceTimersByTimeAsync(0);
};

export const host = { done: vi.fn(), send: vi.fn() };
export const actions = (detail = askDetail(ASK_ID)): Map<string, Action> => new Map(detail.card.actions.map((action) => [action.id, action]));
export function mount(panel: AskPanel, detail = askDetail(ASK_ID), without: string[] = []): HTMLElement | null {
  const known = actions(detail);
  const root = panel.build(detail, (id) => {
    const action = known.get(id);
    if (action === undefined || without.includes(id)) return null;
    const button = document.createElement("button");
    button.dataset.action = id;
    button.textContent = action.label;
    return button;
  });
  if (root !== null) document.body.append(root);
  return root;
}
export const fresh = (): AskPanel => new AskPanel(host);

export function useAskHarness(): void {
  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
    document.body.replaceChildren();
    host.done.mockReset().mockResolvedValue(undefined);
    host.send.mockReset().mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });
}
