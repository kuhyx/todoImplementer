import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { defineNewTask } from "@/components/new-task";
import { routes } from "@/lib/routes";
import { settle } from "@/test/net";
import { card, filesEvent, fill, ids, image, mount, OK, panel, pdf, q, setUp, submit, tearDown, UP } from "@/test/newtask";

beforeEach(() => {
  setUp(defineNewTask);
});
afterEach(tearDown);

describe("ti-new-task", () => {
  it("opens from the + button with the known repos offered and free entry, closes on Escape and the close button", () => {
    const element = mount();
    expect(panel(element).hidden).toBe(true);
    element.defaultRepo = "kuhyx/other";
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    expect(panel(element).hidden).toBe(false);
    expect([...element.querySelectorAll("datalist option")].map((o) => o.getAttribute("value"))).toEqual(["kuhyx/demo", "kuhyx/other"]);
    expect(q<HTMLInputElement>(element, "input[name=repo]").value).toBe("kuhyx/other");
    expect(document.activeElement).toBe(q(element, "input[name=title]"));
    q(element, "[role=dialog]").dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "Escape" }));
    expect(panel(element).hidden).toBe(true);
    element.defaultRepo = "kuhyx/demo";
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    expect(q<HTMLInputElement>(element, "input[name=repo]").value).toBe("kuhyx/other");
    q<HTMLButtonElement>(element, "[data-new-task=cancel]").click();
    expect(panel(element).hidden).toBe(true);
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    q(element, ".nt-scrim").click();
    expect(panel(element).hidden).toBe(true);
  });

  it("focuses the repo first when none is known yet, and Tab stays inside", () => {
    const element = mount();
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    expect(document.activeElement).toBe(q(element, "input[name=repo]"));
    const dialog = q(element, "[role=dialog]");
    const tab = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Tab", shiftKey: true });
    dialog.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(q(element, "[data-new-task=cancel]"));
    dialog.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, key: "a" }));
    expect(panel(element).hidden).toBe(false);
  });

  it("keeps Create disabled with its reason until repo owner/name and a title are there", () => {
    const element = mount();
    expect(submit(element).getAttribute("aria-disabled")).toBe("true");
    expect(submit(element).title).not.toBe("");
    fill(element, "demo", "Fix it");
    expect(submit(element).getAttribute("aria-disabled")).toBe("true");
    fill(element, "kuhyx/demo", ' '.repeat(3));
    expect(submit(element).getAttribute("aria-disabled")).toBe("true");
    fill(element);
    expect(submit(element).getAttribute("aria-disabled")).toBe("false");
    submit(element).click();
    expect(element.querySelector("[aria-busy=true]")).not.toBeNull();
  });

  it("keeps its parts and the repo list when moved or fed the same repos again", () => {
    const element = mount();
    const first = element.querySelector("datalist option");
    element.repos = ["kuhyx/demo", "kuhyx/other"];
    expect(element.querySelector("datalist option")).toBe(first);
    element.remove();
    document.body.append(element);
    expect(element.querySelectorAll("[data-new-task=open]")).toHaveLength(1);
  });

  it("creates the task, shows a loader after 1 s, then closes and names the card to open", async () => {
    const reply = Promise.withResolvers<Response>();
    let up = 0;
    const element = mount({ [`POST ${routes.ownTask}`]: () => reply.promise, [`POST ${routes.upload}`]: () => UP(ids[up++] ?? "") });
    const created = vi.fn();
    element.addEventListener("task-created", (event) => { created((event as CustomEvent<{ id: string }>).detail.id); });
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    fill(element);
    q(element, "[role=dialog]").dispatchEvent(filesEvent("drop", [image(), pdf()]));
    submit(element).click();
    await settle(0);
    expect(submit(element).getAttribute("aria-disabled")).toBe("true");
    expect(q(element, "[data-new-task=open]").getAttribute("aria-disabled")).toBe("true");
    q<HTMLButtonElement>(element, "[data-new-task=cancel]").click();
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    expect(panel(element).hidden).toBe(true);
    submit(element).click();
    expect(element.querySelector(".loader")).toBeNull();
    await settle(1000);
    expect(q(element, ".loader").textContent).toContain(routes.ownTask);
    reply.resolve(Response.json(OK));
    await settle(0);
    const calls = vi.mocked(fetch).mock.calls;
    expect(calls.map(([url]) => url)).toEqual([routes.upload, routes.upload, routes.ownTask]);
    const sent = JSON.parse(calls[2]?.[1]?.body as string) as unknown;
    expect(sent).toEqual({ body: "see pic [Image #1] ", files: [ids[1]], images: [{ upload: ids[0] }], repo: "kuhyx/demo", title: "Fix it" }); // T2321
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:1");
    expect(created).toHaveBeenCalledWith(card?.id);
    expect(panel(element).hidden).toBe(true);
    expect(element.querySelector(".loader")).toBeNull();
    expect(q<HTMLInputElement>(element, "input[name=title]").value).toBe("");
    expect(element.querySelectorAll(".nt-thumbs li")).toHaveLength(0);
  });

  it("keeps everything typed after a refusal, toasts the reason and shakes", async () => {
    const element = mount({ [`POST ${routes.ownTask}`]: () => Response.json({ error: { code: "conflict", message: "twin title" }, ok: false }, { status: 409 }) });
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    fill(element);
    submit(element).click();
    await settle(0);
    expect(document.querySelector("#toasts")?.textContent).toContain("twin title");
    expect(q(element, "[role=dialog]").classList.contains("nt-shake")).toBe(true);
    expect(q<HTMLInputElement>(element, "input[name=title]").value).toBe("Fix it");
    expect(panel(element).hidden).toBe(false);
    expect(submit(element).getAttribute("aria-disabled")).toBe("false");
  });

  it("refuses to post without a CSRF token", () => {
    const element = mount();
    document.head.replaceChildren();
    fill(element);
    submit(element).click();
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
    expect(document.querySelector("#toasts")?.textContent).toContain("CSRF");
  });
});
