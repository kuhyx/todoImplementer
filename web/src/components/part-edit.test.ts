/** Editing a repo part before the run reaches it (856c0f0a): pencil per part, prefilled form, instant title, server truth. */
import { describe, expect, it } from "vitest";

import type { RepoPart, TaskCard } from "@/lib/schemas-common";

import { card, env, fail, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { makeDetail } from "@/test/fixture-detail";
import { settle } from "@/test/net";

useDrawerHarness();

const OPEN = { enabled: true, reason: null } as const;
const PARTS: RepoPart[] = [
  { body: "old text", edit: OPEN, id: "aaaa1111-0", state: "todo", steps: null, title: "Old title" },
  { body: "done text", edit: { enabled: false, reason: "ticked: Ship closes it" }, id: "aaaa1111-1", state: "done", steps: null, title: "Shipped" },
];
const withParts = (parts: RepoPart[]): TaskCard => ({ ...card("backlog"), parts });
const SHOWN = '[data-parts-detail] li[data-id="aaaa1111-0"] .p-title';
const posts = (): { body: unknown; url: string }[] =>
  env.stub.calls.filter((call) => call.init?.method === "POST").map((call) => ({ body: JSON.parse(call.init?.body as string) as unknown, url: call.url }));

async function openWith(c: TaskCard, post: unknown): Promise<void> {
  await open(c, { [`GET /api/task/${c.id}`]: () => makeDetail(c), [`POST /api/task/${c.id}/part-edit`]: post });
}

describe("part edit", () => {
  it("offers a pencil per part, disabled with the server's reason", async () => {
    await openWith(withParts(PARTS), {});
    const pencil = q<HTMLButtonElement>('[data-part-edit="aaaa1111-0"]');
    const locked = q<HTMLButtonElement>('[data-part-edit="aaaa1111-1"]');
    expect(pencil.disabled).toBe(false);
    expect(locked.disabled).toBe(true);
    expect(locked.title).toBe("ticked: Ship closes it");
    expect(locked.getAttribute("aria-label")).toContain("ticked: Ship closes it");
    expect(document.querySelector("[data-part-form]")).toBeNull();
  });

  it("prefills the form, shows the new title at once and posts the edit", async () => {
    const c = withParts(PARTS);
    const saved = withParts([{ ...PARTS[0]!, body: "new text", title: "New title" }, PARTS[1]!]);
    await open(c, {
      [`GET /api/task/${c.id}`]: () => makeDetail(posts().length > 0 ? saved : c),
      [`POST /api/task/${c.id}/part-edit`]: async () => {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        return { ok: true, task: saved };
      },
    });
    q('[data-part-edit="aaaa1111-0"]').click();
    const title = q<HTMLInputElement>('[name="part-title-aaaa1111-0"]');
    const body = q<HTMLTextAreaElement>('[name="part-body-aaaa1111-0"]');
    expect([title.value, body.value]).toEqual(["Old title", "old text"]);
    title.value = "New title";
    body.value = "new text";
    q('[data-part-save="aaaa1111-0"]').click();
    expect(q(SHOWN).textContent).toBe("New title");
    expect(q<HTMLInputElement>('[name="part-title-aaaa1111-0"]').disabled).toBe(true);
    await settle(1000);
    expect(q("[data-part-form]").textContent).toContain("aaaa1111-0");
    await settle(600);
    expect(posts()).toEqual([{ body: { body: "new text", part: "aaaa1111-0", title: "New title" }, url: `/api/task/${c.id}/part-edit` }]);
    expect(document.querySelector("[data-part-form]")).toBeNull();
    expect(q(SHOWN).textContent).toBe("New title");
  });

  it("keeps what kuhy typed across a repaint of the drawer", async () => {
    const c = withParts(PARTS);
    await openWith(c, {});
    q('[data-part-edit="aaaa1111-0"]').click();
    q<HTMLInputElement>('[name="part-title-aaaa1111-0"]').value = "Typing";
    q<HTMLInputElement>('[name="part-title-aaaa1111-0"]').dispatchEvent(new Event("input"));
    env.stub.routes.set(`GET /api/task/${c.id}`, () => makeDetail({ ...c, current: "changed" }));
    await settle(5000);
    expect(q<HTMLInputElement>('[name="part-title-aaaa1111-0"]').value).toBe("Typing");
  });

  it("puts the old title back and keeps the form when the server refuses", async () => {
    await openWith(withParts(PARTS), fail("the run is on this part"));
    q('[data-part-edit="aaaa1111-0"]').click();
    q<HTMLInputElement>('[name="part-title-aaaa1111-0"]').value = "Nope";
    q('[data-part-save="aaaa1111-0"]').click();
    await settle(0);
    expect(document.querySelector("#toasts")?.textContent).toContain("the run is on this part");
    expect(q(SHOWN).textContent).toBe("Old title");
    expect(q<HTMLInputElement>('[name="part-title-aaaa1111-0"]').value).toBe("Nope");
  });

  it("says so when the server answers in a shape it does not know", async () => {
    await openWith(withParts(PARTS), { ok: true });
    q('[data-part-edit="aaaa1111-0"]').click();
    q('[data-part-save="aaaa1111-0"]').click();
    await settle(0);
    expect(document.querySelector("#toasts")?.textContent).toContain("unexpected shape");
  });

  it("sends nothing for an empty title, and cancel closes the form", async () => {
    await openWith(withParts(PARTS), {});
    q('[data-part-edit="aaaa1111-0"]').click();
    q<HTMLInputElement>('[name="part-title-aaaa1111-0"]').value = "  ";
    q('[data-part-save="aaaa1111-0"]').click();
    await settle(0);
    expect(posts()).toEqual([]);
    expect(q('[name="part-title-aaaa1111-0"]').getAttribute("aria-invalid")).toBe("true");
    q('[data-part-cancel="aaaa1111-0"]').click();
    expect(document.querySelector("[data-part-form]")).toBeNull();
  });

  it("ignores a pencil the server does not offer, and opens a part with no text empty", async () => {
    const human: RepoPart = { edit: OPEN, id: "bbbb2222-0", state: "human", steps: null, title: "MANUAL WORK REQUIRED: sign in" };
    await openWith(withParts([...PARTS, human]), {});
    q('[data-part-edit="aaaa1111-1"]').click();
    expect(document.querySelector("[data-part-form]")).toBeNull();
    q('[data-part-edit="bbbb2222-0"]').click();
    expect(q<HTMLTextAreaElement>('[name="part-body-bbbb2222-0"]').value).toBe("");
    expect(document.activeElement).toBe(q('[name="part-title-bbbb2222-0"]'));
  });

  it("closes the form of a part the run reached meanwhile, and refuses without a CSRF token", async () => {
    const c = withParts(PARTS);
    await openWith(c, {});
    q('[data-part-edit="aaaa1111-0"]').click();
    document.head.replaceChildren();
    q('[data-part-save="aaaa1111-0"]').click();
    await settle(0);
    expect(posts()).toEqual([]);
    expect(document.querySelector("#toasts")?.textContent).toContain("CSRF");
    const reached: RepoPart = { ...PARTS[0]!, edit: { enabled: false, reason: "the run is on this part" }, state: "working" };
    env.stub.routes.set(`GET /api/task/${c.id}`, () => makeDetail(withParts([reached, PARTS[1]!])));
    await settle(5000);
    expect(document.querySelector("[data-part-form]")).toBeNull();
  });

  it("[T2614] shows the title without image markdown and edits the note's own title", async () => {
    const source = "Fix ![](https://kuhy-cloud.duckdns.org/todo-images/f1/1.jpg)";
    await openWith(withParts([{ ...PARTS[0]!, title: "Fix", title_source: source }, PARTS[1]!]), {});
    expect(q(SHOWN).textContent).toBe("Fix");
    q('[data-part-edit="aaaa1111-0"]').click();
    expect(q<HTMLInputElement>('[name="part-title-aaaa1111-0"]').value).toBe(source);
  });
});
