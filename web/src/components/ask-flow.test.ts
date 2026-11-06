/** AskPanel send flow: one POST, errors with Retry, Accept all, persisted drafts. */
import { describe, expect, it } from "vitest";

import { field, flush, fresh, host, mount, page, q, type, useAskHarness } from "@/test/ask-harness";
import { ASK_ID, askDetail, askQuestions } from "@/test/fixture-ask";
import { makeDetail } from "@/test/fixture-detail";
import { makeCards } from "@/test/fixtures";

useAskHarness();

describe("all questions", () => {
  it("lists every question with an editable box and sends them all with one Accept all", async () => {
    const detail = { ...askDetail(ASK_ID), questions: askQuestions(3) };
    mount(fresh(), detail);
    q("[data-mode=all]").click();
    expect(q("[data-mode=all]").getAttribute("aria-pressed")).toBe("true");
    expect(document.querySelectorAll(".ask-card textarea")).toHaveLength(3);
    const second = q<HTMLTextAreaElement>("textarea[name=Q2]");
    second.value = "Two";
    second.dispatchEvent(new Event("input"));
    second.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Enter" }));
    expect(host.send).not.toHaveBeenCalled();
    expect(q("[data-ask=accept-all]").textContent).toBe("Accept all 3");
    q("[data-ask=accept-all]").click();
    await flush();
    expect(host.send).toHaveBeenCalledWith(detail.card.id, { Q1: askQuestions(1)[0]?.recommendation, Q2: "Two", Q3: askQuestions(3)[2]?.recommendation });
  });

  it("can switch back to one by one", () => {
    mount(fresh());
    q("[data-mode=all]").click();
    q("[data-mode=step]").click();
    expect(page()).toBe("1 / 5");
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
    expect(page()).toBe("2 / 5");
    q("[data-ask=back]").click();
    expect(field().value).toBe("Draft");
    document.body.replaceChildren();
    localStorage.setItem(`todoimpl.ask.${askDetail(ASK_ID).card.id}.Q1,Q2`, JSON.stringify({ accepted: [], drafts: {}, mode: "step", step: 9 }));
    mount(fresh(), { ...askDetail(ASK_ID), questions: askQuestions(2) });
    expect(page()).toBe("2 / 2");
  });

  it("keeps in-memory progress over a rebuild and forgets it on reset", () => {
    const panel = fresh();
    mount(panel);
    q("[data-ask=accept]").click();
    document.body.replaceChildren();
    mount(panel);
    expect(page()).toBe("2 / 5");
    panel.reset();
    localStorage.clear();
    document.body.replaceChildren();
    mount(panel);
    expect(page()).toBe("1 / 5");
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
