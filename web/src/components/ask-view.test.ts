/** AskPanel step view: prefilled editable box, Enter and swipe accept, other asks, tab choice. */
import { describe, expect, it } from "vitest";

import { field, flush, fresh, host, key, mount, page, q, swipe, type, useAskHarness } from "@/test/ask-harness";
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
    expect(page()).toBe("1 / 5");
    expect(q(".ask-label").textContent).toContain("Recommended");
    expect(document.querySelectorAll(".link, [data-action=spec-answers]")).toHaveLength(0);
    expect(q<HTMLButtonElement>("[data-ask=back]").getAttribute("aria-disabled")).toBe("false");
  });

  it("starts on the first unanswered question and prefills answered ones", () => {
    const detail = askDetail(ASK_ID);
    const [a, b, ...rest] = detail.questions;
    mount(fresh(), { ...detail, questions: [{ ...a!, answer: "Done A" }, { ...b!, answer: "Done B" }, ...rest] });
    expect(page()).toBe("3 / 5");
    q("[data-ask=back]").click();
    expect(field().value).toBe("Done B");
    expect(q(".ask-label").textContent).toBe("Your answer");
  });

  it("edits without a click and accepts with the button, going back keeps the edit", () => {
    const panel = fresh();
    mount(panel);
    type("Mine");
    expect(q(".ask-label").textContent).toBe("Your answer");
    q("[data-ask=accept]").click();
    expect(page()).toBe("2 / 5");
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
    expect(page()).toBe("1 / 5");
    expect(key("Enter").defaultPrevented).toBe(true);
    expect(page()).toBe("2 / 5");
  });

  it("swipes right to accept and left to go back, and cannot go back from the first", () => {
    mount(fresh());
    swipe(-150);
    expect(page()).toBe("1 / 5");
    swipe(150);
    expect(page()).toBe("2 / 5");
    swipe(-150);
    expect(page()).toBe("1 / 5");
  });

  it("sends once, with every answer, when the last one is accepted", async () => {
    const detail = { ...askDetail(ASK_ID), questions: askQuestions(3) };
    const panel = fresh();
    mount(panel, detail);
    type("One");
    key("Enter");
    key("Enter");
    expect(q("[data-ask=accept]").textContent).toBe("Accept and send 3");
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
    expect(page()).toBe("1 / 3");
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
  it("shows read-only questions with the reason when the send action is disabled", () => {
    const detail = askDetail(ASK_ID);
    const blocked = { ...detail, card: { ...detail.card, actions: detail.card.actions.map((a) => (a.id === "spec-answers" ? { ...a, enabled: false, reason: "Claude is working" } : a)) } };
    const panel = fresh();
    mount(panel, blocked);
    expect(panel.interactive).toBe(false);
    expect(q(".ask-reason").textContent).toBe("Claude is working");
    expect(document.querySelectorAll("textarea")).toHaveLength(0);
    expect(document.querySelectorAll(".ask-card")).toHaveLength(5);
    panel.focus();
  });

  it("shows no reason text when the disabled action gives none", () => {
    const detail = askDetail(ASK_ID);
    const blocked = { ...detail, card: { ...detail.card, actions: detail.card.actions.map((a) => (a.id === "spec-answers" ? { ...a, enabled: false, reason: null } : a)) } };
    mount(fresh(), blocked);
    expect(document.querySelectorAll(".ask-reason")).toHaveLength(0);
    expect(document.querySelectorAll(".ask-card")).toHaveLength(5);
  });

  it("shows read-only questions without a reason once the action is gone, with saved answers", () => {
    const detail = askDetail(ASK_ID);
    const answered = { ...detail, card: { ...detail.card, actions: [] }, questions: [{ ...detail.questions[0]!, answer: "Saved" }] };
    mount(fresh(), answered);
    expect(document.querySelectorAll(".ask-reason")).toHaveLength(0);
    expect(q(".ask-card p:last-child").textContent).toBe("Saved");
    expect(q(".ask-label").textContent).toBe("Your answer");
  });

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
