/** AskPanel: card fitting, paging, the phone stepper, Edit and the tab choice. jsdom has no layout, so sizes are faked. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Action } from "@/lib/schemas-common";

import { AskPanel } from "@/components/ask-view";
import { ASK_ID, askDetail, askQuestions, freeDetail } from "@/test/fixture-ask";
import { makeDetail } from "@/test/fixture-detail";
import { makeCards } from "@/test/fixtures";

const GAP = 16;
const size = { cardHeight: 300, height: 700, width: 1100 };
const q = <T extends HTMLElement = HTMLElement>(selector: string): T => {
  const found = document.querySelector<T>(selector);
  if (found === null) throw new Error(selector);
  return found;
};
const shown = (): string[] => [...document.querySelectorAll<HTMLElement>(".ask-card")].filter((card) => !card.hidden).map((card) => card.querySelector("h4")?.textContent.slice(0, 2) ?? "");
const label = (): string => q(".ask-page").textContent;

function fakeLayout(): void {
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(() => size.width);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockImplementation(() => size.height);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function rect(this: HTMLElement) {
    if (this.classList.contains("ask-grid")) return { bottom: size.height } as DOMRect;
    const cols = Number(this.parentElement?.style.getPropertyValue("--cols") ?? 1);
    const index = [...(this.parentElement?.children ?? [])].filter((card) => !(card as HTMLElement).hidden).indexOf(this);
    const row = Math.floor(index / cols);
    return { bottom: (row + 1) * size.cardHeight + row * GAP } as DOMRect;
  });
}

const actions = (detail = askDetail(ASK_ID)): Map<string, Action> => new Map(detail.card.actions.map((action) => [action.id, action]));
function mount(panel: AskPanel, detail = askDetail(ASK_ID), without: string[] = []): HTMLElement | null {
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
  panel.fit();
  return root;
}

beforeEach(() => {
  document.body.replaceChildren();
  Object.assign(size, { cardHeight: 300, height: 700, width: 1100 });
  fakeLayout();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("ask panel", () => {
  it("shows every card on one page when they fit, without a pager", () => {
    mount(new AskPanel());
    expect(shown()).toEqual(["Q1", "Q2", "Q3", "Q4", "Q5"]);
    expect(q(".ask-pager").hidden).toBe(true);
    expect(q(".ask-actions").hidden).toBe(false);
    expect(q(".ask-grid").style.getPropertyValue("--cols")).toBe("3");
    expect(q("[data-action=spec-answers]").textContent).toBe("Send answers");
    expect(q(".ask").dataset.mode).toBe("grid");
  });

  it("pages by what fits, keeps Send answers visible and walks back", () => {
    size.height = 400;
    mount(new AskPanel());
    expect(shown()).toEqual(["Q1", "Q2", "Q3"]);
    expect(label()).toBe("1–3 of 5");
    expect(q<HTMLButtonElement>("[data-ask=back]").disabled).toBe(true);
    expect(q(".ask-actions").hidden).toBe(false);
    q("[data-ask=next]").click();
    expect(shown()).toEqual(["Q4", "Q5"]);
    expect(label()).toBe("4–5 of 5");
    expect(q<HTMLButtonElement>("[data-ask=next]").disabled).toBe(true);
    expect(q<HTMLButtonElement>("[data-ask=back]").disabled).toBe(false);
    q("[data-ask=back]").click();
    expect(shown()).toEqual(["Q1", "Q2", "Q3"]);
  });

  it("steps one question at a time on a phone and offers Send answers on the last", () => {
    size.width = 360;
    mount(new AskPanel());
    expect(shown()).toEqual(["Q1"]);
    expect(label()).toBe("1 / 5");
    expect(q(".ask-actions").hidden).toBe(true);
    for (let step = 0; step < 4; step += 1) q("[data-ask=next]").click();
    expect(shown()).toEqual(["Q5"]);
    expect(label()).toBe("5 / 5");
    expect(q(".ask-actions").hidden).toBe(false);
    expect(q<HTMLButtonElement>("[data-ask=next]").disabled).toBe(true);
  });

  it("uses a single card in one column and a lone card without a label", () => {
    const panel = new AskPanel();
    mount(panel, freeDetail());
    expect(q(".ask-grid").style.getPropertyValue("--cols")).toBe("1");
    expect(label()).toBe("");
    expect(shown()).toEqual(["An"]);
  });

  it("labels a single card page as 'N of M'", () => {
    size.height = 200;
    size.width = 600;
    mount(new AskPanel());
    expect(shown()).toEqual(["Q1"]);
    expect(label()).toBe("1 of 5");
  });

  it("edits a card: textarea after Edit, Use recommended, Done, and one payload", () => {
    const panel = new AskPanel();
    mount(panel);
    const firstField = q<HTMLTextAreaElement>("textarea[name=Q1]");
    expect(firstField.hidden).toBe(true);
    expect(q(".ask-card .ask-label").textContent).toBe("Recommended");
    q(".ask-card .link").click();
    const field = q<HTMLTextAreaElement>("textarea[name=Q1]");
    expect(field.hidden).toBe(false);
    expect(document.activeElement).toBe(field);
    expect(document.querySelectorAll(".ask-card .link")).toHaveLength(2 + 4);
    field.value = "Mine";
    field.dispatchEvent(new Event("input"));
    expect(panel.answers().Q1).toBe("Mine");
    expect(document.querySelectorAll(".ask-card .link")[1]?.textContent).toBe("Use recommended");
    q(".ask-card .link:nth-child(2)").click();
    expect(q<HTMLTextAreaElement>("textarea[name=Q1]").value).toBe(askQuestions(1)[0]?.recommendation);
    q(".ask-card .link").click();
    expect(q<HTMLTextAreaElement>("textarea[name=Q1]").hidden).toBe(true);
    expect(q(".ask-card .ask-label").textContent).toBe("Your answer");
    expect(Object.keys(panel.answers())).toEqual(["Q1", "Q2", "Q3", "Q4", "Q5"]);
  });

  it("shows a saved answer as the answer and drops empty ones from the payload", () => {
    const detail = askDetail(ASK_ID);
    const [first, second] = detail.questions;
    const saved = { ...detail, questions: [{ ...first!, answer: "Saved" }, { ...second!, recommendation: "" }] };
    const panel = new AskPanel();
    mount(panel, saved);
    expect(q(".ask-card .ask-label").textContent).toBe("Your answer");
    expect(panel.answers()).toEqual({ Q1: "Saved" });
  });

  it("is read-only without the Send answers action, and a free ask has no answers", () => {
    const panel = new AskPanel();
    mount(panel, askDetail(ASK_ID), ["spec-answers"]);
    expect(panel.interactive).toBe(false);
    expect(document.querySelectorAll(".ask-card .link")).toHaveLength(0);
    document.body.replaceChildren();
    mount(panel, freeDetail(), ["send"]);
    expect(document.querySelectorAll("textarea")).toHaveLength(0);
    expect(panel.answers()).toEqual({});
    document.body.replaceChildren();
    mount(panel, freeDetail());
    expect(panel.interactive).toBe(true);
    expect(q("textarea[name=ask-send]").getAttribute("placeholder")).toBe("Your answer to Claude");
    expect(panel.answers()).toEqual({});
  });

  it("builds nothing without a question and resets its state", () => {
    const panel = new AskPanel();
    const working = makeCards().find((card) => card.status === "working");
    expect(mount(panel, makeDetail(working ?? makeCards()[0]!))).toBeNull();
    expect(panel.interactive).toBe(false);
    panel.fit();
    expect(panel.answers()).toEqual({});
    mount(panel);
    q(".ask-card .link").click();
    panel.reset();
    document.body.replaceChildren();
    mount(panel, askDetail(ASK_ID));
    expect(q<HTMLTextAreaElement>("textarea[name=Q1]").hidden).toBe(true);
  });

  it("goes back to the first page when the questions shrink below the pager", () => {
    size.height = 400;
    const panel = new AskPanel();
    mount(panel);
    q("[data-ask=next]").click();
    document.body.replaceChildren();
    mount(panel, { ...askDetail(ASK_ID), questions: askQuestions(2) });
    expect(shown()).toEqual(["Q1", "Q2"]);
  });

  it("does nothing while hidden, detached or without a height", () => {
    size.width = 0;
    const panel = new AskPanel();
    mount(panel);
    expect(shown()).toEqual(["Q1", "Q2", "Q3", "Q4", "Q5"]);
    expect(q(".ask").dataset.mode).toBeUndefined();
    size.width = 360;
    size.height = 0;
    panel.fit();
    expect(q(".ask").dataset.mode).toBeUndefined();
    expect(label()).toBe("1 / 5");
    q(".ask").remove();
    panel.fit();
  });

  it("refits on resize and stops watching the replaced grid", () => {
    const callbacks: (() => void)[] = [];
    const disconnect = vi.fn();
    class Observer {
      disconnect = disconnect;
      observe = vi.fn();
      constructor(callback: () => void) {
        callbacks.push(callback);
      }
    }
    vi.stubGlobal("ResizeObserver", Observer);
    const panel = new AskPanel();
    mount(panel);
    size.height = 400;
    callbacks[0]?.();
    expect(shown()).toEqual(["Q1", "Q2", "Q3"]);
    mount(panel);
    expect(disconnect).toHaveBeenCalledTimes(1);
  });

  it("opens Questions when an answer is needed and returns to Activity once it is given", () => {
    const panel = new AskPanel();
    const spec = askDetail(ASK_ID);
    expect(panel.tabFor(spec, "activity")).toBe("questions");
    expect(panel.tabFor(spec, "activity")).toBe("activity");
    expect(panel.tabFor(spec, "questions")).toBe("questions");
    const answered = { ...spec, card: { ...spec.card, actions: spec.card.actions.filter((action) => action.id !== "spec-answers") } };
    expect(panel.tabFor(answered, "questions")).toBe("activity");
    expect(panel.tabFor(answered, "plan")).toBe("plan");
    expect(panel.tabFor(answered, "questions")).toBe("questions");
    expect(panel.tabFor(freeDetail(), "activity")).toBe("questions");
    const working = makeCards().find((card) => card.status === "working");
    expect(panel.tabFor(makeDetail(working ?? makeCards()[0]!), "questions")).toBe("activity");
  });
});
