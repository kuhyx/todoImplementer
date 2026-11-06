/** AskPanel send flow: one POST, errors with Retry, Accept all, persisted drafts. */
import { describe, expect, it } from "vitest";

import { at, field, flush, fresh, host, mount, q, type, useAskHarness } from "@/test/ask-harness";
import { ASK_ID, askDetail, askQuestions } from "@/test/fixture-ask";
import { makeDetail } from "@/test/fixture-detail";
import { makeCards } from "@/test/fixtures";

useAskHarness();

describe("all questions", () => {
  it("lists every question with an editable box and sends them all with one Accept all", async () => {
    const detail = { ...askDetail(ASK_ID), questions: askQuestions(3) };
    mount(fresh(), detail);
    q("[data-ask-mode]").click();
    expect(q("[data-ask-mode]").getAttribute("aria-label")).toBe("One question at a time");
    expect(document.querySelectorAll(".ask-card textarea")).toHaveLength(3);
    const second = q<HTMLTextAreaElement>("textarea[name=Q2]");
    second.value = "Two";
    second.dispatchEvent(new Event("input"));
    second.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Enter" }));
    expect(host.send).not.toHaveBeenCalled();
    expect(q("[data-ask=accept-all]").getAttribute("aria-label")).toBe("OK, send all 3");
    expect(q("[data-ask=accept-all]").textContent).toBe("");
    q("[data-ask=accept-all]").click();
    await flush();
    expect(host.send).toHaveBeenCalledWith(detail.card.id, { Q1: askQuestions(1)[0]?.recommendation, Q2: "Two", Q3: askQuestions(3)[2]?.recommendation });
  });

  it("always opens one question at a time, even after All questions was the last view", () => {
    const panel = fresh();
    mount(panel);
    q("[data-ask-mode]").click();
    panel.reset();
    document.body.replaceChildren();
    mount(panel);
    expect(document.querySelectorAll(".ask-step")).toHaveLength(1);
    expect(q("[data-ask-mode]").getAttribute("aria-label")).toBe("All questions");
    expect(document.querySelectorAll(".ask-card")).toHaveLength(1);
  });

  it("can switch back to one by one", () => {
    mount(fresh());
    q("[data-ask-mode]").click();
    q("[data-ask-mode]").click();
    expect(at()).toBe("Q1");
  });
});

describe("persistence", () => {
  it("restores drafts, step and mode after a reload and clamps a stale step", () => {
    const first = fresh();
    mount(first);
    type("Draft");
    q("[data-ask=accept]").click();
    document.body.replaceChildren();
    mount(fresh());
    expect(at()).toBe("Q2");
    q("[data-ask=back]").click();
    expect(field().value).toBe("Draft");
    document.body.replaceChildren();
    localStorage.setItem(`todoimpl.ask.${askDetail(ASK_ID).card.id}.Q1,Q2`, JSON.stringify({ drafts: {}, mode: "all", step: 9 }));
    mount(fresh(), { ...askDetail(ASK_ID), questions: askQuestions(2) });
    expect(at()).toBe("Q2");
  });

  it("keeps in-memory progress over a rebuild and forgets it on reset", () => {
    const panel = fresh();
    mount(panel);
    q("[data-ask=accept]").click();
    document.body.replaceChildren();
    mount(panel);
    expect(at()).toBe("Q2");
    panel.reset();
    localStorage.clear();
    document.body.replaceChildren();
    mount(panel);
    expect(at()).toBe("Q1");
  });
});

describe("after the send", () => {
  it("does not repaint when the refreshed card no longer asks anything", async () => {
    const panel = fresh();
    const detail = { ...askDetail(ASK_ID), questions: askQuestions(1) };
    mount(panel, detail);
    const working = makeCards().find((card) => card.status === "working");
    host.done.mockImplementation(() => {
      document.body.replaceChildren();
      expect(mount(panel, makeDetail(working ?? makeCards()[0]!))).toBeNull();
      return Promise.resolve();
    });
    q("[data-ask=accept]").click();
    await flush();
    expect(host.done).toHaveBeenCalledTimes(1);
    expect(document.querySelectorAll("textarea")).toHaveLength(0);
  });
});
