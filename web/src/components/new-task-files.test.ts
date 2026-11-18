/** <ti-new-task> attachments: any file by picker, camera, paste or drop, size caps, uploads, mobile layout. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { defineNewTask } from "@/components/new-task";
import { MAX_FILE, MAX_TOTAL } from "@/lib/newtask-api";
import { routes } from "@/lib/routes";
import { settle } from "@/test/net";
import { filesEvent, fill, ids, image, mount, OK, panel, pdf, q, setUp, sized, submit, tearDown, UP } from "@/test/newtask";

beforeEach(() => {
  setUp(defineNewTask);
});
afterEach(tearDown);

describe("ti-new-task attachments", () => {
  it("takes any file from the picker, a paste and a drop: thumbnails for images, an icon and the name for the rest", () => {
    const element = mount();
    const picker = q<HTMLInputElement>(element, "input[name=files]");
    expect(picker.hasAttribute("accept")).toBe(false);
    expect(picker.multiple).toBe(true);
    const click = vi.spyOn(picker, "click");
    q<HTMLButtonElement>(element, "[data-new-task=pick]").click();
    expect(click).toHaveBeenCalledOnce();
    Object.defineProperty(picker, "files", { configurable: true, value: [pdf(), pdf("a.zip", "application/zip"), image()] });
    picker.dispatchEvent(new Event("change"));
    const dialog = q(element, "[role=dialog]");
    const paste = filesEvent("paste", [image("b.png")]);
    dialog.dispatchEvent(paste);
    expect(paste.defaultPrevented).toBe(true);
    const over = new Event("dragover", { bubbles: true, cancelable: true });
    dialog.dispatchEvent(over);
    expect(over.defaultPrevented).toBe(true);
    dialog.dispatchEvent(filesEvent("drop", [pdf("notes.docx", ""), pdf("odd.xyz", ""), pdf("noext", "")]));
    expect([...element.querySelectorAll<HTMLImageElement>(".nt-thumbs img")].map((img) => img.src)).toEqual(["blob:1", "blob:2"]);
    const names = [...element.querySelectorAll(".nt-thumbs .nt-file")].map((li) => li.textContent);
    expect(names).toEqual(["spec.pdf", "a.zip", "notes.docx", "odd.xyz", "noext"]);
    expect(element.querySelectorAll(".nt-thumbs .nt-file svg")).toHaveLength(5);
    q<HTMLButtonElement>(element, "[data-new-task=remove]").click();
    expect(element.querySelectorAll(".nt-thumbs li")).toHaveLength(6);
    const second = element.querySelectorAll<HTMLButtonElement>("[data-new-task=remove]")[1];
    second?.click();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:1");
    expect(element.querySelectorAll(".nt-thumbs img")).toHaveLength(1);
  });

  it("offers the camera through its own picker", () => {
    const element = mount();
    const camera = q<HTMLInputElement>(element, "input[name=camera]");
    expect(camera.accept).toBe("image/*");
    expect(camera.getAttribute("capture")).toBe("environment");
    const click = vi.spyOn(camera, "click");
    q<HTMLButtonElement>(element, "[data-new-task=camera]").click();
    expect(click).toHaveBeenCalledOnce();
    Object.defineProperty(camera, "files", { configurable: true, value: [image("cam.jpg")] });
    camera.dispatchEvent(new Event("change"));
    expect(element.querySelectorAll(".nt-thumbs img")).toHaveLength(1);
  });

  it("lets a text paste through and ignores events without files", () => {
    const element = mount();
    const dialog = q(element, "[role=dialog]");
    const plain = new Event("paste", { bubbles: true, cancelable: true });
    dialog.dispatchEvent(plain);
    expect(plain.defaultPrevented).toBe(false);
    dialog.dispatchEvent(new Event("drop", { bubbles: true, cancelable: true }));
    const picker = q<HTMLInputElement>(element, "input[name=files]");
    Object.defineProperty(picker, "files", { configurable: true, value: null });
    picker.dispatchEvent(new Event("change"));
    expect(element.querySelectorAll(".nt-thumbs li")).toHaveLength(0);
  });

  it("refuses a file over 100 MB and one that would take the task over 500 MB, naming it", () => {
    const element = mount();
    const dialog = q(element, "[role=dialog]");
    dialog.dispatchEvent(filesEvent("drop", [sized("huge.mov", MAX_FILE + 1), sized("ok.bin", MAX_FILE)]));
    expect(document.querySelector("#toasts")?.textContent).toContain("huge.mov");
    expect(element.querySelectorAll(".nt-thumbs li")).toHaveLength(1);
    const many = Array.from({ length: MAX_TOTAL / MAX_FILE }, (_, n) => sized(`p${String(n)}.bin`, MAX_FILE));
    dialog.dispatchEvent(filesEvent("drop", many));
    expect(element.querySelectorAll(".nt-thumbs li")).toHaveLength(MAX_TOTAL / MAX_FILE);
    expect(document.querySelector("#toasts")?.textContent).toContain(`p${String(MAX_TOTAL / MAX_FILE - 1)}.bin`);
  });

  it("names the file it uploads in the loader, and a retry after a refusal does not upload it again", async () => {
    const upload = Promise.withResolvers<Response>();
    let posts = 0;
    const element = mount({
      [`POST ${routes.ownTask}`]: () => (posts++ === 0 ? Response.json({ error: { code: "conflict", message: "twin" }, ok: false }, { status: 409 }) : OK),
      [`POST ${routes.upload}`]: () => upload.promise,
    });
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    fill(element);
    q(element, "[role=dialog]").dispatchEvent(filesEvent("drop", [pdf("big.pdf")]));
    submit(element).click();
    await settle(1000);
    expect(q(element, ".loader").textContent).toContain("big.pdf");
    upload.resolve(Response.json(UP(ids[0] ?? "")));
    await settle(0);
    expect(document.querySelector("#toasts")?.textContent).toContain("twin");
    submit(element).click();
    await settle(0);
    const urls = vi.mocked(fetch).mock.calls.map(([url]) => url);
    expect(urls).toEqual([routes.upload, routes.ownTask, routes.ownTask]);
    expect(panel(element).hidden).toBe(true);
  });

  it("toasts an upload the server refuses and keeps the files", async () => {
    const element = mount({ [`POST ${routes.upload}`]: () => Response.json({ error: { code: "internal", message: "big.pdf could not be stored" }, ok: false }, { status: 500 }) });
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    fill(element);
    q(element, "[role=dialog]").dispatchEvent(filesEvent("drop", [pdf("big.pdf")]));
    submit(element).click();
    await settle(0);
    expect(document.querySelector("#toasts")?.textContent).toContain("could not be stored");
    expect(element.querySelectorAll(".nt-thumbs li")).toHaveLength(1);
  });

  it("grows the details field with its text and follows the visible viewport while open", () => {
    const listeners = new Map<string, () => void>();
    const viewport = { addEventListener: vi.fn((type: string, function_: () => void) => listeners.set(type, function_)), height: 400, offsetTop: 30, removeEventListener: vi.fn() };
    vi.stubGlobal("visualViewport", viewport);
    const element = mount();
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    const dialog = q(element, "[role=dialog]");
    expect(dialog.style.getPropertyValue("--nt-vh")).toBe("400px");
    expect(dialog.style.getPropertyValue("--nt-top")).toBe("30px");
    viewport.height = 250;
    listeners.get("resize")?.();
    expect(dialog.style.getPropertyValue("--nt-vh")).toBe("250px");
    const body = q<HTMLTextAreaElement>(element, "textarea[name=body]");
    Object.defineProperty(body, "scrollHeight", { configurable: true, value: 900 });
    const into = vi.fn();
    body.scrollIntoView = into;
    body.value = "line\n".repeat(40);
    body.dispatchEvent(new Event("input", { bubbles: true }));
    expect(body.style.height).toBe("900px");
    expect(into).toHaveBeenCalledWith({ block: "nearest" });
    q<HTMLButtonElement>(element, "[data-new-task=cancel]").click();
    expect(viewport.removeEventListener).toHaveBeenCalledWith("resize", listeners.get("resize"));
  });

});
