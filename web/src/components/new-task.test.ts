import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { defineNewTask, MAX_IMAGES, TiNewTask } from "@/components/new-task";
import { routes } from "@/lib/routes";
import { makeCards } from "@/test/fixtures";
import { settle, stubFetch } from "@/test/net";

const [card] = makeCards();
const OK = { note: "abcd1234", ok: true, started: true, task: card };
const q = <T extends Element = HTMLElement>(root: ParentNode, sel: string): T => {
  const found = root.querySelector<T>(sel);
  if (found === null) throw new Error(`no ${sel}`);
  return found;
};
const image = (name = "a.png"): File => new File(["px"], name, { type: "image/png" });

function mount(routes_: Record<string, unknown> = {}): TiNewTask {
  stubFetch(routes_);
  const element = document.createElement("ti-new-task") as TiNewTask;
  element.encode = (file: Blob) => Promise.resolve(`b64-${String(file.size)}`);
  document.body.append(element);
  element.repos = ["kuhyx/demo", "kuhyx/other"];
  return element;
}

function fill(element: TiNewTask, repo = "kuhyx/demo", title = "Fix it"): void {
  for (const [sel, value] of [["input[name=repo]", repo], ["input[name=title]", title], ["textarea[name=body]", "see pic"]] as const) {
    const field = q<HTMLInputElement>(element, sel);
    field.value = value;
    field.dispatchEvent(new Event("input", { bubbles: true }));
  }
}

const submit = (element: TiNewTask): HTMLButtonElement => q<HTMLButtonElement>(element, "[data-new-task=submit]");
const panel = (element: TiNewTask): HTMLElement => q(element, ".nt-panel");

function filesEvent(type: "drop" | "paste", files: File[]): Event {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperty(event, type === "paste" ? "clipboardData" : "dataTransfer", { value: { files } });
  return event;
}

beforeEach(() => {
  vi.useFakeTimers();
  document.head.innerHTML = '<meta name="todoimpl-csrf" content="tok">';
  document.body.replaceChildren();
  defineNewTask();
  defineNewTask();
});
afterEach(() => {
  document.body.replaceChildren();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

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

  it("takes pictures from the picker, a paste and a drop, shows thumbnails and removes one", async () => {
    const element = mount();
    const picker = q<HTMLInputElement>(element, "input[type=file]");
    expect(picker.accept).toBe("image/*");
    expect(picker.multiple).toBe(true);
    const click = vi.spyOn(picker, "click");
    q<HTMLButtonElement>(element, "[data-new-task=pick]").click();
    expect(click).toHaveBeenCalledOnce();
    Object.defineProperty(picker, "files", { configurable: true, value: [image()] });
    picker.dispatchEvent(new Event("change"));
    const dialog = q(element, "[role=dialog]");
    const paste = filesEvent("paste", [image("b.png"), new File(["t"], "t.txt", { type: "text/plain" })]);
    dialog.dispatchEvent(paste);
    expect(paste.defaultPrevented).toBe(true);
    const over = new Event("dragover", { bubbles: true, cancelable: true });
    dialog.dispatchEvent(over);
    expect(over.defaultPrevented).toBe(true);
    dialog.dispatchEvent(filesEvent("drop", [image("c.png")]));
    await settle(0);
    const thumbs = element.querySelectorAll<HTMLImageElement>(".nt-thumbs img");
    expect([...thumbs].map((img) => img.src)).toEqual(Array.from({ length: 3 }, () => "data:image/jpeg;base64,b64-2"));
    q<HTMLButtonElement>(element, "[data-new-task=remove]").click();
    expect(element.querySelectorAll(".nt-thumbs img")).toHaveLength(2);
  });

  it("lets a text paste through and ignores events without files", () => {
    const element = mount();
    const dialog = q(element, "[role=dialog]");
    const plain = new Event("paste", { bubbles: true, cancelable: true });
    dialog.dispatchEvent(plain);
    expect(plain.defaultPrevented).toBe(false);
    dialog.dispatchEvent(new Event("drop", { bubbles: true, cancelable: true }));
    const picker = q<HTMLInputElement>(element, "input[type=file]");
    Object.defineProperty(picker, "files", { configurable: true, value: null });
    picker.dispatchEvent(new Event("change"));
    expect(element.querySelectorAll(".nt-thumbs img")).toHaveLength(0);
  });

  it("stops at the picture limit and waits for pictures still being prepared", async () => {
    const element = mount();
    const slow = Promise.withResolvers<string>();
    element.encode = () => slow.promise;
    fill(element);
    q(element, "[role=dialog]").dispatchEvent(filesEvent("drop", [image()]));
    expect(submit(element).getAttribute("aria-disabled")).toBe("true");
    slow.resolve("slow");
    await settle(0);
    expect(submit(element).getAttribute("aria-disabled")).toBe("false");
    element.encode = () => Promise.resolve("x");
    q(element, "[role=dialog]").dispatchEvent(filesEvent("drop", Array.from({ length: MAX_IMAGES + 3 }, () => image())));
    await settle(0);
    expect(element.querySelectorAll(".nt-thumbs img")).toHaveLength(MAX_IMAGES);
    expect(q(element, "[data-new-task=pick]").getAttribute("aria-disabled")).toBe("true");
    const click = vi.spyOn(q<HTMLInputElement>(element, "input[type=file]"), "click");
    q<HTMLButtonElement>(element, "[data-new-task=pick]").click();
    expect(click).not.toHaveBeenCalled();
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

  it("toasts a picture the browser cannot read", async () => {
    const element = mount();
    element.encode = () => Promise.reject(new Error("cannot decode"));
    q(element, "[role=dialog]").dispatchEvent(filesEvent("drop", [image()]));
    await settle(0);
    expect(document.querySelector("#toasts")?.textContent).toContain("cannot decode");
  });

  it("creates the task, shows a loader after 1 s, then closes and names the card to open", async () => {
    const reply = Promise.withResolvers<Response>();
    const element = mount({ [`POST ${routes.ownTask}`]: () => reply.promise });
    const created = vi.fn();
    element.addEventListener("task-created", (event) => { created((event as CustomEvent<{ id: string }>).detail.id); });
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    fill(element);
    q(element, "[role=dialog]").dispatchEvent(filesEvent("drop", [image()]));
    await settle(0);
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
    const sent = JSON.parse(vi.mocked(fetch).mock.calls[0]?.[1]?.body as string) as unknown;
    expect(sent).toEqual({ body: "see pic", images: [{ data_b64: "b64-2" }], repo: "kuhyx/demo", title: "Fix it" });
    expect(vi.mocked(fetch)).toHaveBeenCalledOnce();
    expect(created).toHaveBeenCalledWith(card?.id);
    expect(panel(element).hidden).toBe(true);
    expect(element.querySelector(".loader")).toBeNull();
    expect(q<HTMLInputElement>(element, "input[name=title]").value).toBe("");
    expect(element.querySelectorAll(".nt-thumbs img")).toHaveLength(0);
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
