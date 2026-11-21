/** Send to Claude with images: paste or pick png/jpeg/webp/gif, #N chips, `[Image #N]` in the text, upload ids in the POST (T2320). */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MAX_IMAGE, MAX_IMAGES } from "@/lib/image-tags";
import { routes } from "@/lib/routes";
import { env, json, open, q, useDrawerHarness } from "@/test/drawer-harness";
import { freeDetail } from "@/test/fixture-ask";
import { settle } from "@/test/net";
import { filesEvent, image, pdf, sized } from "@/test/newtask";

useDrawerHarness();

const ID = (n: number): string => String(n).repeat(32);
const detail = freeDetail();
const { id } = detail.card;
const box = (): HTMLTextAreaElement => q<HTMLTextAreaElement>("textarea[name=send]");
const chips = (): string[] => [...document.querySelectorAll(".send-images li")].map((li) => li.querySelector(".chip-n")?.textContent ?? "");
const toasts = (): string => document.querySelector("#toasts")?.textContent ?? "";
const posts = (): { body: unknown; url: string }[] =>
  env.stub.calls.filter((call) => call.init?.method === "POST").map((call) => ({ body: call.init?.body, url: call.url }));

async function openSend(send: () => unknown = () => ({ ok: true, task: detail.card })): Promise<void> {
  let up = 0;
  await open(detail.card, {
    [`GET /api/task/${id}`]: detail,
    [`POST ${routes.post(id, "send")}`]: send,
    [`POST ${routes.upload}`]: () => ({ ok: true, upload: { id: ID(++up), name: "x", size: 1 } }),
  });
}

function paste(files: File[]): Event {
  const event = filesEvent("paste", files);
  box().dispatchEvent(event);
  return event;
}

beforeEach(() => {
  let made = 0;
  URL.createObjectURL = vi.fn(() => `blob:${String(++made)}`);
  URL.revokeObjectURL = vi.fn();
});

describe("[T2320] Send to Claude takes images", () => {
  it("[T2320] a pasted screenshot becomes chip #1 and `[Image #1]` at the cursor", async () => {
    await openSend();
    box().value = "look  here";
    box().setSelectionRange(5, 5);
    const event = paste([image("shot.png")]);
    expect(event.defaultPrevented).toBe(true);
    expect(box().value).toBe("look [Image #1] here");
    expect(chips()).toEqual(["#1"]);
    expect(q<HTMLImageElement>(".send-images img").src).toBe("blob:1");
    const plain = new Event("paste", { bubbles: true, cancelable: true });
    box().dispatchEvent(plain);
    expect(plain.defaultPrevented).toBe(false);
  });

  it("[T2320] the picker adds images and names the reason for each refused file", async () => {
    await openSend();
    const input = q<HTMLInputElement>("input[name=send-images]");
    expect(input.accept).toBe("image/png,image/jpeg,image/webp,image/gif");
    expect(input.multiple).toBe(true);
    const click = vi.spyOn(input, "click");
    q<HTMLButtonElement>("[data-send-images=pick]").click();
    expect(click).toHaveBeenCalledOnce();
    const big = new File(["px"], "big.png", { type: "image/png" });
    Object.defineProperty(big, "size", { value: MAX_IMAGE + 1 });
    Object.defineProperty(input, "files", { configurable: true, value: [image("a.webp"), pdf(), big, sized("b.gif", 1)] });
    input.dispatchEvent(new Event("change"));
    expect(chips()).toEqual(["#1"]);
    expect(toasts()).toContain("spec.pdf: not a PNG, JPEG, WebP or GIF image");
    expect(toasts()).toContain("big.png: over 10 MB");
    expect(toasts()).toContain("b.gif: not a PNG, JPEG, WebP or GIF image");
    Object.defineProperty(input, "files", { configurable: true, value: null });
    input.dispatchEvent(new Event("change"));
    paste(Array.from({ length: MAX_IMAGES + 1 }, (_, n) => image(`p${String(n)}.png`)));
    expect(chips()).toHaveLength(MAX_IMAGES);
    expect(toasts()).toContain(`p${String(MAX_IMAGES - 1)}.png: at most ${String(MAX_IMAGES)} images per message`);
  });

  it("[T2320] removing a chip drops its tag and renumbers the rest", async () => {
    await openSend();
    paste([image("a.png")]);
    box().value += "a ";
    paste([image("b.png")]);
    box().value += "b ";
    paste([image("c.png")]);
    expect(box().value).toBe("[Image #1] a [Image #2] b [Image #3] ");
    q<HTMLButtonElement>(".send-images li:first-child [data-send-images=remove]").click();
    expect(box().value).toBe("a [Image #1] b [Image #2] ");
    expect(chips()).toEqual(["#1", "#2"]);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:1");
    q<HTMLButtonElement>(".send-images li:last-child [data-send-images=remove]").click();
    expect(box().value).toBe("a [Image #1] b ");
  });

  it("[T2320] Send uploads each image, posts their ids and clears the chips", async () => {
    await openSend();
    box().value = "see ";
    paste([image("a.png"), image("b.png")]);
    q("[data-action=send]").click();
    await settle(0);
    expect(posts().map((p) => p.url)).toEqual([routes.upload, routes.upload, routes.post(id, "send")]);
    const sent = JSON.parse(posts()[2]?.body as string) as unknown;
    expect(sent).toEqual({ images: [{ upload: ID(1) }, { upload: ID(2) }], text: "see [Image #1] [Image #2]" });
    expect(chips()).toEqual([]);
    expect(box().value).toBe("");
  });

  it("[T2320] a refused send keeps the chips and a retry uploads nothing twice", async () => {
    let tries = 0;
    await openSend(() => (tries++ === 0 ? json({ error: { code: "disabled", message: "closing" }, ok: false }, 409) : { ok: true, task: detail.card }));
    paste([image("a.png")]);
    q("[data-action=send]").click();
    await settle(0);
    expect(toasts()).toContain("closing");
    expect(chips()).toEqual(["#1"]);
    q("[data-action=send]").click();
    await settle(0);
    expect(posts().map((p) => p.url)).toEqual([routes.upload, routes.post(id, "send"), routes.post(id, "send")]);
    expect(chips()).toEqual([]);
  });
});
