/** AskPanel step view: prefilled editable box, Enter and swipe accept, other asks, tab choice. */
import { describe, expect, it } from "vitest";

import { at, field, flush, fresh, host, key, mount, q, swipe, type, useAskHarness } from "@/test/ask-harness";
import { ASK_ID, askDetail, askQuestions, freeDetail } from "@/test/fixture-ask";
import { makeDetail } from "@/test/fixture-detail";
import { makeCards } from "@/test/fixtures";

useAskHarness();

describe("step view", () => {
  it("shows the first question with its recommendation in a focused, editable box and no Edit link", () => {
    const panel = fresh();
    mount(panel);
    panel.focus();
    expect(q("h4").textContent).toBe("Q1 · Verification");
    expect(field().value).toBe(askQuestions(1)[0]?.recommendation);
    expect(field().readOnly).toBe(false);
    expect(document.activeElement).toBe(field());
    expect(at()).toBe("Q1");
    expect(document.querySelectorAll(".link, [data-action=spec-answers]")).toHaveLength(0);
    expect(q<HTMLButtonElement>("[data-ask=back]").getAttribute("aria-disabled")).toBe("false");
  });

  it("starts on the first unanswered question and prefills answered ones", () => {
    const detail = askDetail(ASK_ID);
    const [a, b, ...rest] = detail.questions;
    mount(fresh(), { ...detail, questions: [{ ...a!, answer: "Done A" }, { ...b!, answer: "Done B" }, ...rest] });
    expect(at()).toBe("Q3");
    q("[data-ask=back]").click();
    expect(field().value).toBe("Done B");
  });

  it("edits without a click and accepts with the button, going back keeps the edit", () => {
    const panel = fresh();
    mount(panel);
    type("Mine");
    q("[data-ask=accept]").click();
    expect(at()).toBe("Q2");
    expect(field().value).toBe(askQuestions(2)[1]?.recommendation);
    q("[data-ask=back]").click();
    expect(field().value).toBe("Mine");
    expect(host.send).not.toHaveBeenCalled();
  });

  it("accepts on Enter but not on Shift+Enter or while composing", () => {
    mount(fresh());
    expect(key("Enter", { shiftKey: true }).defaultPrevented).toBe(false);
    expect(key("Enter", { isComposing: true }).defaultPrevented).toBe(false);
    expect(key("a").defaultPrevented).toBe(false);
    expect(at()).toBe("Q1");
    expect(key("Enter").defaultPrevented).toBe(true);
    expect(at()).toBe("Q2");
  });

  it("swipes right to accept and left to go back, and cannot go back from the first", () => {
    mount(fresh());
    swipe(-150);
    expect(at()).toBe("Q1");
    swipe(150);
    expect(at()).toBe("Q2");
    swipe(-150);
    expect(at()).toBe("Q1");
  });

  it("sends once, with every answer, when the last one is accepted", async () => {
    const detail = { ...askDetail(ASK_ID), questions: askQuestions(3) };
    const panel = fresh();
    mount(panel, detail);
    type("One");
    key("Enter");
    key("Enter");
    expect(q("[data-ask=accept]").getAttribute("aria-label")).toBe("OK");
    const gate = Promise.withResolvers<undefined>();
    host.send.mockReturnValue(gate.promise);
    key("Enter");
    expect(q(".loader").textContent).toBe("Sending 3 answers…");
    key("Enter");
    swipe(150);
    q("[data-ask=accept]").click();
    expect(host.send).toHaveBeenCalledTimes(1);
    expect(host.send).toHaveBeenCalledWith(detail.card.id, { Q1: "One", Q2: askQuestions(2)[1]?.recommendation, Q3: askQuestions(3)[2]?.recommendation });
    gate.resolve(undefined);
    await flush();
    expect(host.done).toHaveBeenCalledWith(detail.card.id);
    expect(q(".ask-status").textContent).toBe("");
    expect(localStorage).toHaveLength(0);
    expect(at()).toBe("Q1");
  });

  it("keeps the answers and offers Retry when the send fails", async () => {
    const detail = { ...askDetail(ASK_ID), questions: askQuestions(1) };
    host.send.mockRejectedValueOnce(new Error("HTTP 500"));
    mount(fresh(), detail);
    type("Keep me");
    key("Enter");
    await flush();
    expect(q("[role=alert]").textContent).toContain("HTTP 500");
    expect(field().value).toBe("Keep me");
    expect(host.done).not.toHaveBeenCalled();
    q("[data-ask=retry]").click();
    await flush();
    expect(host.send).toHaveBeenCalledTimes(2);
    expect(host.send).toHaveBeenLastCalledWith(detail.card.id, { Q1: "Keep me" });
    expect(host.done).toHaveBeenCalledTimes(1);
  });

  it("refuses to send when every answer is empty", async () => {
    const detail = { ...askDetail(ASK_ID), questions: [{ answer: null, body: "", id: "Q1", recommendation: "", title: "Storage" }] };
    mount(fresh(), detail);
    expect(document.querySelectorAll(".ask-body")).toHaveLength(0);
    key("Enter");
    await flush();
    expect(q("[role=alert]").textContent).toContain("Write at least one answer first.");
    expect(host.send).not.toHaveBeenCalled();
  });
});

describe("other asks", () => {
  it("answers a free question from its own box with the card's send button", () => {
    const panel = fresh();
    mount(panel, freeDetail());
    expect(panel.interactive).toBe(true);
    expect(q("textarea[name=ask-send]").getAttribute("placeholder")).toBe("Your answer to Claude");
    expect(q("[data-action=send]").textContent).toBe("Send to Claude");
    document.body.replaceChildren();
    mount(panel, freeDetail(), ["send"]);
    expect(panel.interactive).toBe(false);
    expect(document.querySelectorAll("textarea")).toHaveLength(0);
  });

  it("builds nothing without a question", () => {
    const panel = fresh();
    const working = makeCards().find((card) => card.status === "working");
    expect(mount(panel, makeDetail(working ?? makeCards()[0]!))).toBeNull();
    expect(panel.interactive).toBe(false);
    panel.focus();
  });

  it("does not focus a detached or hidden panel", () => {
    const panel = fresh();
    const root = mount(panel);
    root!.hidden = true;
    panel.focus();
    expect(document.activeElement).not.toBe(field());
    root!.remove();
    panel.focus();
  });
});

describe("tab choice", () => {
  it("opens Questions when an answer is needed and returns to Activity once it is given", () => {
    const panel = fresh();
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
