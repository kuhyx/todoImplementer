/** A plain Claude question goes through the same one-question view as spec questions, and OK posts the card's send action. */
import { describe, expect, it } from "vitest";

import { at, field, flush, fresh, host, key, mount, q, type, useAskHarness, withAction } from "@/test/ask-harness";
import { freeDetail } from "@/test/fixture-ask";

useAskHarness();

const TEXT = "Claude asked a question: answer it with Send to Claude";

describe("plain Claude question", () => {
  it("[T1805] uses the one-question view: no old free card, no Send to Claude button", () => {
    const panel = fresh();
    mount(panel, freeDetail());
    expect(panel.interactive).toBe(true);
    expect(document.querySelectorAll(".ask-step")).toHaveLength(1);
    expect(at()).toBe("Q1");
    expect(q(".ask-title").textContent).toBe("Q1 · Claude asks");
    expect(q(".ask-body").textContent).toBe(TEXT);
    expect(field().name).toBe("Q1");
    expect(field().value).toBe("");
    expect(document.querySelector("textarea[name=ask-send]")).toBeNull();
    expect(document.querySelector("[data-action=send]")).toBeNull();
    expect(q("[data-ask=accept]").getAttribute("aria-label")).toBe("OK");
    expect(panel.switcher).toBeNull();
  });

  it("[T1805] OK posts the answer as the card's send action, then refreshes the card", async () => {
    mount(fresh(), freeDetail());
    type("  use port 8790 ");
    q("[data-ask=accept]").click();
    await flush();
    expect(host.reply).toHaveBeenCalledWith(freeDetail().card.id, "use port 8790");
    expect(host.send).not.toHaveBeenCalled();
    expect(host.done).toHaveBeenCalledTimes(1);
  });

  it("[T1805] refuses an empty answer and keeps a failed one with Retry", async () => {
    mount(fresh(), freeDetail());
    key("Enter");
    await flush();
    expect(q("[role=alert]").textContent).toContain("Write at least one answer first.");
    expect(host.reply).not.toHaveBeenCalled();
    type("Later");
    host.reply.mockRejectedValueOnce(new Error("HTTP 500"));
    key("Enter");
    await flush();
    expect(q("[role=alert]").textContent).toContain("HTTP 500");
    q("[data-ask=retry]").click();
    await flush();
    expect(host.reply).toHaveBeenLastCalledWith(freeDetail().card.id, "Later");
  });

  it("[T1805] keeps the answer during a usage limit and sends it once send is enabled", async () => {
    const panel = fresh();
    const limited = withAction({ enabled: false, reason: "usage limit until 01:10" }, freeDetail(), "send");
    mount(panel, limited);
    expect(q(".ask-reason").textContent).toContain("usage limit until 01:10");
    type("Kept");
    key("Enter");
    await flush();
    expect(host.reply).not.toHaveBeenCalled();
    expect(JSON.parse(localStorage.getItem(`todoimpl.ask.${limited.card.id}.free.Q1`) ?? "{}")).toMatchObject({ drafts: { Q1: "Kept" }, queued: true });
    document.body.replaceChildren();
    mount(panel, limited);
    await flush();
    expect(host.reply).not.toHaveBeenCalled();
    expect(field().value).toBe("Kept");
    document.body.replaceChildren();
    mount(panel, freeDetail());
    await flush();
    expect(host.reply).toHaveBeenCalledTimes(1);
    expect(host.reply).toHaveBeenCalledWith(limited.card.id, "Kept");
    expect(host.done).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(`todoimpl.ask.${limited.card.id}.free.Q1`)).toBeNull();
  });

  it("[T1805] says it is not waiting when the card has no send action", () => {
    const detail = freeDetail();
    mount(fresh(), { ...detail, card: { ...detail.card, actions: [] } });
    expect(q(".ask-reason").textContent).toBe("These questions are not waiting for an answer.");
  });
});
