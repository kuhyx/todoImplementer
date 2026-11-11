/** The ask block's buttons in the drawer: choice, take recommended, command, screenshot, undo (C1-C7, C10, C11). */
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AskItem } from "@/lib/schemas-asks";

import { card, env, fail, json, q, useDrawerHarness } from "@/test/drawer-harness";
import { makeDetail } from "@/test/fixture-detail";
import { settle, stubFetch } from "@/test/net";

useDrawerHarness();

const item = (over: Partial<AskItem> & Pick<AskItem, "id" | "type">): AskItem => ({ risk: "risky", state: "open", title: `T ${over.id}`, ...over });
const choice = (id: string, state: AskItem["state"] = "open", answer?: string): AskItem =>
  item({ id, options: ["red", "blue", "green"], recommended: "blue", state, type: "choice", ...(answer !== undefined && { answer }) });

async function openWith(items: AskItem[], extra: Record<string, unknown> = {}): Promise<string> {
  const c = card("needs_you");
  const detail = { ...makeDetail(c), ask_items: items };
  env.stub = stubFetch({ [`GET /api/task/${c.id}`]: () => detail, ...extra });
  env.drawer.open(c.id, document.querySelector("#opener"));
  await settle(0);
  return c.id;
}
const posts = (): string[] => env.stub.calls.filter((call) => call.init?.method === "POST").map((call) => `${call.url} ${(call.init?.body as string)}`);

const write = vi.fn((text: string) => Promise.resolve(text.length > 0));
beforeEach(() => {
  write.mockReset().mockImplementation((text: string) => Promise.resolve(text.length > 0));
  vi.stubGlobal("navigator", { clipboard: { writeText: write } });
});

describe("ask items", () => {
  it("C1: one button per option and one Take recommended, no text box in the asks", async () => {
    await openWith([choice("c1")]);
    expect(document.querySelectorAll("[data-asks] [data-option]")).toHaveLength(3);
    expect(document.querySelectorAll("[data-take]")).toHaveLength(1);
    expect(document.querySelector("[data-asks] textarea")).toBeNull();
    expect(q("[data-option=blue]").classList.contains("btn--primary")).toBe(true);
  });

  it("renders nothing when the card has no asks", async () => {
    await openWith([]);
    expect(document.querySelector("[data-asks]")).toBeNull();
  });

  it("C2: an option shows answered at once, then posts it", async () => {
    const id = card("needs_you").id;
    const gate = Promise.withResolvers<unknown>();
    await openWith([choice("c1")], { [`POST /api/task/${id}/ask/answer`]: () => gate.promise });
    q("[data-option=red]").click();
    expect(q("[data-ask=c1]").dataset.state).toBe("answered");
    expect(q("[data-option=red]").getAttribute("aria-pressed")).toBe("true");
    gate.resolve(json({ ok: true }));
    await settle(0);
    expect(posts()).toEqual([`/api/task/${id}/ask/answer {"ask":"c1","option":"red"}`]);
  });

  it("C3: Take recommended answers every open choice with one POST", async () => {
    const id = card("needs_you").id;
    await openWith([choice("c1"), choice("c2", "answered", "red"), choice("c3")], { [`POST /api/task/${id}/ask/take-recommended`]: () => json({ ok: true }) });
    q("[data-take]").click();
    expect(document.querySelectorAll("[data-state=answered]")).toHaveLength(3);
    expect(document.querySelector("[data-take]")).toBeNull();
    await settle(0);
    expect(posts()).toEqual([`/api/task/${id}/ask/take-recommended {}`]);
  });

  it("a refused click puts the row back and says why", async () => {
    const id = card("needs_you").id;
    await openWith([choice("c1")], { [`POST /api/task/${id}/ask/answer`]: fail("not an option of this ask") });
    q("[data-option=red]").click();
    await settle(0);
    expect(q("[data-ask=c1]").dataset.state).toBe("open");
    expect(document.body.textContent).toContain("not an option of this ask");
  });

  it("C5: RUN posts and shows the output tail with the exit code", async () => {
    const id = card("needs_you").id;
    const result = { capped: false, exit: 0, tail: "line one" };
    await openWith([item({ command: "make fast", id: "k1", mode: "run", type: "command" })], { [`POST /api/task/${id}/ask/run`]: () => json({ ok: true, result }) });
    q("[data-run=run]").click();
    await settle(0);
    expect(q("pre.ask-out").textContent).toBe("line one\nexit 0");
    expect(posts()).toEqual([`/api/task/${id}/ask/run {"add":false,"ask":"k1"}`]);
  });

  it("C6: a command not listed offers add-and-run and posts add true; C8 shows the cap", async () => {
    const id = card("needs_you").id;
    const result = { capped: true, exit: 124, tail: "" };
    await openWith([item({ command: "sleep 99", id: "k1", mode: "add_run", type: "command" })], { [`POST /api/task/${id}/ask/run`]: () => json({ ok: true, result }) });
    expect(q("[data-run]").getAttribute("aria-label")).toBe("Add to allow-list and run");
    q("[data-run]").click();
    await settle(0);
    expect(q("pre.ask-out").textContent).toBe("exit 124 (60 s cap)");
    expect(posts()[0]).toContain('"add":true');
  });

  it("C7/C9: a never-add or root command gets only the warning button and copy text", async () => {
    await openWith([item({ command: "! textgate approve", id: "k1", mode: "terminal", type: "command", warning: true })]);
    expect(document.querySelector("[data-run]")).toBeNull();
    q("[data-warning]").click();
    q("[data-copy]").click();
    expect(write).toHaveBeenCalledTimes(2);
    expect(write).toHaveBeenCalledWith("! textgate approve");
    expect(posts()).toEqual([]);
  });

  it("a blocked clipboard shows the command in a toast", async () => {
    write.mockImplementation(() => Promise.reject(new Error("no")));
    await openWith([item({ command: "sudo ls", id: "k1", mode: "terminal", type: "command", warning: true })]);
    q("[data-copy]").click();
    await settle(0);
    expect(document.body.textContent).toContain("sudo ls");
  });

  it("C10: a screenshot shows the picture with Approve and Reject; verdicts post", async () => {
    const id = card("needs_you").id;
    await openWith([item({ id: "s1", shot: "shots/a.png", type: "screenshot" })], {
      [`POST /api/task/${id}/ask/approve`]: () => json({ ok: true }),
      [`POST /api/task/${id}/ask/reject`]: () => json({ ok: true }),
    });
    expect(q<HTMLImageElement>("img.ask-shot").getAttribute("src")).toBe(`/api/task/${id}/shot/a.png`);
    q("[data-reject]").click();
    expect(q("[data-ask=s1]").dataset.state).toBe("rejected");
    q("[data-approve]").click();
    expect(q("[data-ask=s1]").dataset.state).toBe("approved");
    expect(document.querySelector("[data-approve]")).toBeNull();
    await settle(0);
    expect(posts().map((p) => p.split(" ", 1)[0]?.split("/").pop())).toEqual(["reject", "approve"]);
  });

  it("a screenshot ask without a file shows no picture", async () => {
    await openWith([item({ id: "s1", type: "screenshot" })]);
    expect(document.querySelector("img.ask-shot")).toBeNull();
  });

  it("C11: an auto-adopted choice shows Undo, which reopens it", async () => {
    const id = card("needs_you").id;
    await openWith([choice("c1", "auto", "blue")], { [`POST /api/task/${id}/ask/undo`]: () => json({ ok: true }) });
    expect(q("[data-ask=c1]").dataset.state).toBe("auto");
    q("[data-undo=c1]").click();
    expect(q("[data-ask=c1]").dataset.state).toBe("open");
    await settle(0);
    expect(posts()).toEqual([`/api/task/${id}/ask/undo {"ask":"c1"}`]);
  });

  it("refuses to post without a CSRF token", async () => {
    await openWith([choice("c1")]);
    document.head.replaceChildren();
    q("[data-option=red]").click();
    expect(document.body.textContent).toContain("no CSRF token");
    expect(posts()).toEqual([]);
  });
});
