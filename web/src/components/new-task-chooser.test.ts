/** <ti-new-task> repo chooser: none, all or several repos, folding, one description box, one send per repo. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { defineNewTask } from "@/components/new-task";
import { routes } from "@/lib/routes";
import { settle } from "@/test/net";
import { card, choose, filesEvent, fill, ids, image, mount, OK, panel, q, setUp, submit, tearDown, UP } from "@/test/newtask";

beforeEach(() => {
  setUp(defineNewTask);
});
afterEach(tearDown);

const sentBodies = (): unknown[] => vi.mocked(fetch).mock.calls.filter(([url]) => url === routes.ownTask).map(([, init]) => JSON.parse(init?.body as string) as unknown);
const folded = (element: HTMLElement): HTMLButtonElement => q<HTMLButtonElement>(element, "[data-new-task=scope]");
const chips = (element: HTMLElement): HTMLElement => q(element, ".nt-chips");

describe("ti-new-task repo chooser", () => {
  it("folds to one row once a repo is picked; the row opens it again with the pick kept, and a second repo joins", () => {
    const element = mount();
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    expect(folded(element).hidden).toBe(true);
    choose(element, "kuhyx/demo");
    expect(chips(element).hidden).toBe(true);
    expect(folded(element).hidden).toBe(false);
    expect(folded(element).textContent).toBe("kuhyx/demo");
    expect(document.activeElement).toBe(q(element, "textarea[name=body]"));
    folded(element).click();
    expect(chips(element).hidden).toBe(false);
    expect(q(element, '[data-repo="kuhyx/demo"]').getAttribute("aria-pressed")).toBe("true");
    q<HTMLButtonElement>(element, '[data-repo="kuhyx/other"]').click();
    expect(folded(element).textContent).toBe("kuhyx/demokuhyx/other");
    choose(element, "kuhyx/demo", "kuhyx/other");
    expect(chips(element).hidden).toBe(false);
    expect(submit(element).getAttribute("aria-disabled")).toBe("true");
  });

  it("shows none and all as icons in the folded row and drops repo picks for them", () => {
    const element = mount();
    choose(element, "kuhyx/demo", "all");
    expect(folded(element).textContent).toBe("");
    expect(folded(element).querySelector("svg")).not.toBeNull();
    folded(element).click();
    expect(q(element, "[data-scope=all]").getAttribute("aria-pressed")).toBe("true");
    expect(q(element, '[data-repo="kuhyx/demo"]').getAttribute("aria-pressed")).toBe("false");
    q<HTMLButtonElement>(element, "[data-scope=none]").click();
    expect(folded(element).getAttribute("aria-label")).toContain(q(element, "[data-scope=none]").getAttribute("aria-label"));
  });

  it("filters the chips by the typed text and adds a typed owner/name that is not on the board", () => {
    const element = mount();
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    const typed = q<HTMLInputElement>(element, "input[name=repo]");
    typed.value = "oth";
    typed.dispatchEvent(new Event("input", { bubbles: true }));
    expect([...element.querySelectorAll<HTMLElement>("[data-repo]")].map((chip) => chip.hidden)).toEqual([true, false]);
    typed.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Enter" }));
    expect(folded(element).textContent).toBe("kuhyx/other");
    folded(element).click();
    typed.value = "bad name";
    typed.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Enter" }));
    expect(chips(element).hidden).toBe(false);
    typed.value = "kuhyx/new";
    typed.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Enter" }));
    expect(folded(element).textContent).toBe("kuhyx/otherkuhyx/new");
    typed.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "a" }));
  });

  it("[T2399] sends one task per picked repo, titled by the first line, the image uploaded once", async () => {
    let up = 0;
    const element = mount({ [`POST ${routes.ownTask}`]: OK, [`POST ${routes.upload}`]: () => UP(ids[up++] ?? "") });
    const created = vi.fn();
    element.addEventListener("task-created", created);
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    fill(element, "Fix it\nmore\nlines", ["kuhyx/demo", "kuhyx/other"]);
    q(element, "[role=dialog]").dispatchEvent(filesEvent("drop", [image()]));
    submit(element).click();
    await settle(0);
    expect(sentBodies()).toEqual([
      { body: "more\nlines [Image #1]", images: [{ upload: ids[0] }], repo: "kuhyx/demo", title: "Fix it" },
      { body: "more\nlines [Image #1]", images: [{ upload: ids[0] }], repo: "kuhyx/other", title: "Fix it" },
    ]);
    expect(up).toBe(1);
    expect(created).toHaveBeenCalledOnce();
    expect(panel(element).hidden).toBe(true);
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    expect(folded(element).hidden).toBe(true);
  });

  it("sends all as one repo-less note, and keeps a long first line in the body", async () => {
    const element = mount({ [`POST ${routes.ownTask}`]: { note: OK.note, ok: true, started: false } });
    const long = "x".repeat(250);
    fill(element, `${long}\nrest`, ["all"]);
    submit(element).click();
    await settle(0);
    expect(sentBodies()).toEqual([{ body: `${long}\nrest`, title: "x".repeat(200) }]);
  });

  it("after one of two sends is refused, OK sends only the repo not sent yet", async () => {
    let posts = 0;
    const refuse = (): Response => Response.json({ error: { code: "conflict", message: "twin" }, ok: false }, { status: 409 });
    const element = mount({ [`POST ${routes.ownTask}`]: () => (posts++ === 1 ? refuse() : Response.json({ ...OK, task: card })) });
    fill(element, "Fix it", ["kuhyx/demo", "kuhyx/other"]);
    submit(element).click();
    await settle(0);
    expect(document.querySelector("#toasts")?.textContent).toContain("twin");
    expect(q(element, "[role=dialog]").classList.contains("nt-shake")).toBe(true);
    expect(folded(element).textContent).toBe("kuhyx/other");
    submit(element).click();
    await settle(0);
    expect(sentBodies().map((body) => (body as { repo: string }).repo)).toEqual(["kuhyx/demo", "kuhyx/other", "kuhyx/other"]);
  });

  it("puts close and OK in the attachments row, at its end", () => {
    const element = mount();
    const bar = q(element, ".nt-bar");
    const order = [...bar.querySelectorAll("[data-new-task], .nt-thumbs")].map((node) => node.getAttribute("data-new-task") ?? "thumbs");
    expect(order).toEqual(["pick", "camera", "thumbs", "cancel", "submit"]);
    expect(q<HTMLTextAreaElement>(element, "textarea[name=body]").rows).toBe(18);
  });
});
