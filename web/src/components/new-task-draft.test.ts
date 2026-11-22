/**
 * [T2493] <ti-new-task> keeps its draft across a reload: a "bad token" refusal (the server restarted, so the
 * page's CSRF token is stale), the page's own reload on a new build, a killed browser. Text and the repo picks
 * live in localStorage, the files in IndexedDB; only a task that went out clears it. A second element stands in
 * for the reloaded page.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { defineNewTask, type TiNewTask } from "@/components/new-task";
import { dropState, keepFiles, loadKept, loadState } from "@/lib/newtask-draft";
import { routes } from "@/lib/routes";
import { fakeIdb, installFakeIdb } from "@/test/fake-idb";
import { settle, stubFetch } from "@/test/net";
import { choose, filesEvent, fill, ids, image, mount, OK, panel, pdf, q, setUp, submit, tearDown, UP } from "@/test/newtask";

const BAD_TOKEN = { [`POST ${routes.ownTask}`]: () => Response.json({ error: { code: "forbidden", message: "bad token" }, ok: false }, { status: 403 }), [`POST ${routes.upload}`]: () => UP(ids[0] ?? "") };

const TEXT = "Fix it\nsee pic [Image #1] ";

async function loadFiles(): Promise<{ file: File; image: boolean }[]> {
  const kept = await loadKept();
  return kept.files;
}

beforeEach(() => {
  setUp(defineNewTask);
  installFakeIdb();
});
afterEach(tearDown);

const body = (element: TiNewTask): HTMLTextAreaElement => q<HTMLTextAreaElement>(element, "textarea[name=body]");
const names = (element: TiNewTask): (null | string)[] => [...element.querySelectorAll(".nt-thumbs img, .nt-thumbs .nt-file")].map((shown) => shown.getAttribute("title"));

/** Opens the dialog (once the page read its draft), picks kuhyx/demo, types and attaches an image and a PDF. */
async function draft(): Promise<TiNewTask> {
  const element = mount(BAD_TOKEN);
  await settle(0);
  q<HTMLButtonElement>(element, "[data-new-task=open]").click();
  fill(element, "Fix it\nsee pic");
  q(element, "[role=dialog]").dispatchEvent(filesEvent("drop", [image("shot.png"), pdf("spec.pdf")]));
  return element;
}

/** The page reloads: the old element goes, a new one mounts and reads the draft. */
async function reload(old: TiNewTask): Promise<TiNewTask> {
  old.remove();
  const element = mount(BAD_TOKEN);
  await settle(0);
  return element;
}

describe("ti-new-task draft", () => {
  it("[T2493] a bad-token refusal, then a reload, gives back the text, the repo picks and every file", async () => {
    const first = await draft();
    submit(first).click();
    await settle(0);
    expect(document.querySelector("#toasts")?.textContent).toContain("bad token");
    const element = await reload(first);
    expect(panel(element).hidden).toBe(false); // it was open when the page went away
    expect(body(element).value).toBe(TEXT);
    expect(names(element)).toEqual(["shot.png", "spec.pdf"]);
    expect(element.querySelectorAll(".nt-thumbs img")).toHaveLength(1);
    expect(q(element, "[data-new-task=scope]").getAttribute("aria-label")).toBe("Repos: kuhyx/demo");
    expect(submit(element).getAttribute("aria-disabled")).toBe("false");
  });

  it("[T2493] a browser killed before localStorage committed (Chromium writes it seconds late) gets the text from IndexedDB", async () => {
    const first = await draft();
    await settle(0);
    localStorage.clear();
    const element = await reload(first);
    expect(panel(element).hidden).toBe(false);
    expect(body(element).value).toBe(TEXT);
    expect(names(element)).toEqual(["shot.png", "spec.pdf"]);
    expect(q(element, "[data-new-task=scope]").getAttribute("aria-label")).toBe("Repos: kuhyx/demo");
  });

  it("[T2493] an older IndexedDB copy (its write failed) loses to the fresher localStorage one", async () => {
    const first = await draft();
    await settle(0);
    fakeIdb.fail = "tx";
    fill(first, "Newer text", []);
    await settle(0);
    const element = await reload(first);
    expect(body(element).value).toBe("Newer text");
    const kept = await loadKept();
    expect(kept.state?.body).toBe("Newer text"); // the next save after the failure caught up
  });

  it("[T2493] a closed dialog keeps its draft; a reload restores it closed and Open shows it", async () => {
    const first = await draft();
    q<HTMLButtonElement>(first, "[data-new-task=cancel]").click();
    const element = await reload(first);
    expect(panel(element).hidden).toBe(true);
    q<HTMLButtonElement>(element, "[data-new-task=open]").click();
    expect(body(element).value).toBe(TEXT);
    expect(names(element)).toEqual(["shot.png", "spec.pdf"]);
  });

  it("[T2493] a restored draft uploads its files again and a task that went out clears it", async () => {
    const element = await reload(await draft());
    const stub = stubFetch({ [`POST ${routes.ownTask}`]: OK, [`POST ${routes.upload}`]: () => UP(ids[1] ?? "") });
    submit(element).click();
    await settle(0);
    expect(panel(element).hidden).toBe(true);
    await settle(0);
    expect(stub.calls.map(({ url }) => url)).toEqual([routes.upload, routes.upload, routes.ownTask]);
    expect(loadState()).toBeNull();
    expect(await loadFiles()).toEqual([]);
    const next = await reload(element);
    q<HTMLButtonElement>(next, "[data-new-task=open]").click();
    expect(body(next).value).toBe("");
    expect(names(next)).toEqual([]);
  });

  it("[T2493] typed text and a typed repo come back; files the user added before the load are kept", async () => {
    const first = mount();
    q<HTMLButtonElement>(first, "[data-new-task=open]").click();
    const typed = q<HTMLInputElement>(first, "input[name=repo]");
    typed.value = "kuhyx/new";
    typed.dispatchEvent(new Event("input"));
    fill(first, "Only text", []);
    first.remove();
    const element = mount();
    expect(q<HTMLInputElement>(element, "input[name=repo]").value).toBe("kuhyx/new");
    expect(body(element).value).toBe("Only text");
    q(element, "[role=dialog]").dispatchEvent(filesEvent("drop", [pdf("mine.pdf")]));
    await settle(0);
    expect(names(element)).toEqual(["mine.pdf"]);
    const saved = await loadFiles();
    expect(saved.map(({ file }) => file.name)).toEqual(["mine.pdf"]); // saved once the load is in
  });

  it("[T2493] none and all come back folded", async () => {
    const first = await draft();
    choose(first, "all");
    const element = await reload(first);
    expect(q(element, "[data-new-task=scope]").getAttribute("aria-label")).toContain("All repos");
  });

  it("[T2493] storage that fails never breaks the dialog: no IndexedDB, a failed open, a failed write, bad JSON", async () => {
    fakeIdb.fail = "open";
    expect(await loadFiles()).toEqual([]);
    fakeIdb.fail = "tx";
    await keepFiles([{ file: pdf(), image: false }]);
    expect(await loadFiles()).toEqual([]);
    localStorage.setItem("todoimpl.newtask.draft", "{not json");
    expect(loadState()).toBeNull();
    localStorage.setItem("todoimpl.newtask.draft", JSON.stringify({ body: 1 }));
    expect(loadState()).toBeNull();
    const blocked = (): never => { throw new Error("blocked"); };
    const storage = Object.getPrototypeOf(localStorage) as Storage;
    const saved = { get: storage.getItem, remove: storage.removeItem, set: storage.setItem };
    Object.assign(storage, { getItem: blocked, removeItem: blocked, setItem: blocked });
    try {
      expect(loadState()).toBeNull();
      dropState();
      const element = await draft();
      expect(body(element).value).toBe(TEXT);
    } finally {
      Object.assign(storage, { getItem: saved.get, removeItem: saved.remove, setItem: saved.set });
    }
    Reflect.deleteProperty(globalThis, "indexedDB");
    expect(await loadFiles()).toEqual([]);
    await keepFiles([]);
  });
});
