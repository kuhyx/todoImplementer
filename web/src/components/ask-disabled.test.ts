/** The question flow when the server cannot take the answers yet (or never will): still one question, answers kept and sent later. */
import { describe, expect, it } from "vitest";

import { at, field, flush, fresh, host, key, mount, q, type, useAskHarness, withAction } from "@/test/ask-harness";
import { ASK_ID, askDetail, askQuestions } from "@/test/fixture-ask";

useAskHarness();

describe("disabled send action", () => {
  it("[T1801] questions card opens on one question even when spec-answers is disabled", () => {
    const panel = fresh();
    mount(panel, withAction({ enabled: false, reason: "Claude is working" }));
    panel.focus();
    expect(panel.interactive).toBe(true);
    expect(document.querySelectorAll(".ask-card")).toHaveLength(1);
    expect(q("h4").textContent).toBe("Q1 · Verification");
    expect(document.activeElement).toBe(field());
    expect(at()).toBe("Q1");
    expect(q(".ask-reason").textContent).toContain("Claude is working");
    expect(q("[data-ask=accept]").getAttribute("aria-label")).toBe("OK");
  });

  it("keeps the answers of a disabled card and sends them once the action is enabled", async () => {
    const panel = fresh();
    const detail = { ...withAction({ enabled: false, reason: "Claude is working" }), questions: askQuestions(2) };
    mount(panel, detail);
    type("Kept");
    key("Enter");
    key("Enter");
    await flush();
    expect(host.send).not.toHaveBeenCalled();
    expect(q(".ask-reason").textContent).toContain("Claude is working");
    expect(JSON.parse(localStorage.getItem(`todoimpl.ask.${detail.card.id}.Q1,Q2`) ?? "{}")).toMatchObject({ drafts: { Q1: "Kept" }, queued: true });
    document.body.replaceChildren();
    mount(panel, detail);
    await flush();
    expect(host.send).not.toHaveBeenCalled();
    document.body.replaceChildren();
    mount(panel, { ...detail, card: { ...detail.card, actions: askDetail(ASK_ID).card.actions } });
    await flush();
    expect(host.send).toHaveBeenCalledTimes(1);
    expect(host.send).toHaveBeenCalledWith(detail.card.id, { Q1: "Kept", Q2: askQuestions(2)[1]?.recommendation });
    expect(host.done).toHaveBeenCalledTimes(1);
  });

  it("does not resend a queued failure on every rebuild", async () => {
    const panel = fresh();
    const detail = { ...askDetail(ASK_ID), questions: askQuestions(1) };
    mount(panel, { ...withAction({ enabled: false, reason: "x" }), questions: askQuestions(1) });
    key("Enter");
    host.send.mockRejectedValueOnce(new Error("HTTP 500"));
    document.body.replaceChildren();
    mount(panel, detail);
    await flush();
    document.body.replaceChildren();
    mount(panel, detail);
    await flush();
    expect(host.send).toHaveBeenCalledTimes(1);
    expect(q("[role=alert]").textContent).toContain("HTTP 500");
  });

  it("shows the step view with a generic note when the disabled action gives no reason", () => {
    mount(fresh(), withAction({ enabled: false, reason: null }));
    expect(q(".ask-reason").textContent).toBe("Your answers are kept here and sent as soon as Claude can take them.");
    expect(document.querySelectorAll(".ask-card")).toHaveLength(1);
  });

  it("walks only the open questions, skipping answered ones, and sends all with the last OK", async () => {
    const detail = askDetail(ASK_ID);
    const [a, b, c, d, fifth] = detail.questions;
    const questions = [{ ...a!, answer: "A" }, b!, { ...c!, answer: "C" }, d!, { ...fifth!, answer: "E" }];
    mount(fresh(), { ...detail, questions });
    expect(at()).toBe("Q2");
    key("Enter");
    expect(at()).toBe("Q4");
    key("Enter");
    await flush();
    expect(host.send).toHaveBeenCalledWith(detail.card.id, { Q1: "A", Q2: b?.recommendation, Q3: "C", Q4: d?.recommendation, Q5: "E" });
  });

  it("has no read-only list when the action is gone: the step view stays and nothing is sent", async () => {
    const detail = askDetail(ASK_ID);
    const answered = { ...detail, card: { ...detail.card, actions: [] }, questions: [{ ...detail.questions[0]!, answer: "Saved" }] };
    mount(fresh(), answered);
    expect(field().value).toBe("Saved");
    expect(q(".ask-reason").textContent).toBe("These questions are not waiting for an answer.");
    key("Enter");
    await flush();
    expect(host.send).not.toHaveBeenCalled();
    expect(JSON.parse(localStorage.getItem(`todoimpl.ask.${detail.card.id}.Q1`) ?? "{}")).toMatchObject({ queued: false });
  });
});
