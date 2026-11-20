/** <ti-new-task> numbered images: #N chips, `[Image #N]` in the details, `images: [{upload}]` in the POST (T2321). */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { defineNewTask } from "@/components/new-task";
import { MAX_IMAGE, MAX_IMAGES } from "@/lib/image-tags";
import { routes } from "@/lib/routes";
import { settle } from "@/test/net";
import { filesEvent, fill, ids, image, mount, OK, pdf, q, setUp, submit, tearDown, UP } from "@/test/newtask";

beforeEach(() => {
  setUp(defineNewTask);
});
afterEach(tearDown);

const labels = (root: ParentNode): string[] => [...root.querySelectorAll(".nt-thumbs li")].map((li) => li.querySelector(".chip-n")?.textContent ?? "-");

describe("[T2321] New task numbers its images", () => {
  it("[T2321] a pasted image is chip #1 and `[Image #1]` at the cursor; other files get no number", () => {
    const element = mount();
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    const body = q<HTMLTextAreaElement>(element, "textarea[name=body]");
    body.value = "header wraps";
    body.setSelectionRange(6, 6);
    q(element, "[role=dialog]").dispatchEvent(filesEvent("paste", [image("shot.png"), pdf()]));
    expect(body.value).toBe("header [Image #1] wraps");
    expect(labels(element)).toEqual(["#1", "-"]);
  });

  it("[T2321] removing an image drops its tag and renumbers; a big or ninth image stays a plain file", () => {
    const element = mount();
    const body = q<HTMLTextAreaElement>(element, "textarea[name=body]");
    const dialog = q(element, "[role=dialog]");
    dialog.dispatchEvent(filesEvent("drop", [image("a.png"), image("b.jpg")]));
    expect(body.value).toBe("[Image #1] [Image #2] ");
    q<HTMLButtonElement>(element, "[data-new-task=remove]").click();
    expect(body.value).toBe("[Image #1] ");
    expect(labels(element)).toEqual(["#1"]);
    const big = image("big.png");
    Object.defineProperty(big, "size", { value: MAX_IMAGE + 1 });
    dialog.dispatchEvent(filesEvent("drop", [big, ...Array.from({ length: MAX_IMAGES }, (_, n) => image(`p${String(n)}.png`))]));
    expect(labels(element).filter((label) => label === "-")).toHaveLength(2);
    expect(labels(element).at(-1)).toBe("-");
  });

  it("[T2321] Create posts the images as upload refs and the rest as files", async () => {
    let up = 0;
    const element = mount({ [`POST ${routes.ownTask}`]: OK, [`POST ${routes.upload}`]: () => UP(ids[up++] ?? "") });
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    fill(element);
    q(element, "[role=dialog]").dispatchEvent(filesEvent("drop", [pdf(), image()]));
    submit(element).click();
    await settle(0);
    const calls = vi.mocked(fetch).mock.calls;
    const sent = JSON.parse(calls[2]?.[1]?.body as string) as unknown;
    expect(sent).toEqual({ body: "see pic [Image #1]", files: [ids[0]], images: [{ upload: ids[1] }], repo: "kuhyx/demo", title: "Fix it" });
  });
});
